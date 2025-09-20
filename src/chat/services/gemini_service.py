# -*- coding: utf-8 -*-

import os
import logging
from typing import Optional, Dict, List
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
from datetime import datetime, timezone, timedelta
import re
import random

import requests
from PIL import Image
import io

# 导入新库
from google import genai
from google.genai import types
from google.api_core import exceptions as google_exceptions
from google.genai import errors as genai_errors

# 导入数据库管理器和提示词配置
from src import config
from src.chat.utils.database import chat_db_manager
from src.chat.config import chat_config as app_config
from src.chat.config.emoji_config import EMOJI_MAPPINGS
from src.chat.features.affection.service.affection_service import affection_service
from src.chat.services.regex_service import regex_service
from src.chat.services.prompt_service import prompt_service
from src.chat.services.key_rotation_service import KeyRotationService, NoAvailableKeyError
 
log = logging.getLogger(__name__)

# --- 设置专门用于记录无效 API 密钥的 logger ---
# 确保 data 目录存在
if not os.path.exists('data'):
    os.makedirs('data')

# 创建一个新的 logger 实例
invalid_key_logger = logging.getLogger('invalid_api_keys')
invalid_key_logger.setLevel(logging.ERROR)

# 创建文件处理器，将日志写入到 data/invalid_api_keys.log
# 使用 a 模式表示追加写入
fh = logging.FileHandler('data/invalid_api_keys.log', mode='a', encoding='utf-8')
fh.setLevel(logging.ERROR)

# 创建格式化器并设置
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
fh.setFormatter(formatter)

# 为 logger 添加处理器
# 防止重复添加处理器
if not invalid_key_logger.handlers:
    invalid_key_logger.addHandler(fh)

class GeminiService:
    """Gemini AI 服务类，使用数据库存储用户对话上下文"""

    def __init__(self):

        # --- 密钥轮换服务 ---
        google_api_keys_str = os.getenv("GOOGLE_API_KEYS_LIST", "")
        if not google_api_keys_str:
            log.error("GOOGLE_API_KEYS_LIST 环境变量未设置！服务将无法运行。")
            # 在这种严重配置错误下，抛出异常以阻止应用启动
            raise ValueError("GOOGLE_API_KEYS_LIST is not set.")
        
        # 先移除整个字符串两端的空格和引号，以支持 "key1,key2" 格式
        processed_keys_str = google_api_keys_str.strip().strip('"')
        api_keys = [key.strip() for key in processed_keys_str.split(',') if key.strip()]
        self.key_rotation_service = KeyRotationService(api_keys)
        log.info(f"GeminiService 初始化并由 KeyRotationService 管理 {len(api_keys)} 个密钥。")

        self.model_name = app_config.GEMINI_MODEL
        self.executor = ThreadPoolExecutor(max_workers=10)
        self.user_request_timestamps: Dict[int, List[datetime]] = {}
        self.safety_settings = [
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
                threshold=types.HarmBlockThreshold.BLOCK_NONE,
            ),
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                threshold=types.HarmBlockThreshold.BLOCK_NONE,
            ),
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                threshold=types.HarmBlockThreshold.BLOCK_NONE,
            ),
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                threshold=types.HarmBlockThreshold.BLOCK_NONE,
            ),
        ]

    def _create_client_with_key(self, api_key: str):
        """使用给定的 API 密钥动态创建一个 Gemini 客户端实例。"""
        base_url = os.getenv('GEMINI_API_BASE_URL')
        if base_url:
            log.info(f"使用自定义 Gemini API 端点: {base_url}")
            # 根据用户提供的文档，正确的方法是使用 types.HttpOptions
            # Cloudflare Worker 需要 /gemini 后缀，所以我们不移除它
            http_options = types.HttpOptions(base_url=base_url)
            return genai.Client(api_key=api_key, http_options=http_options)
        else:
            log.info("使用默认 Gemini API 端点。")
            return genai.Client(api_key=api_key)

    async def get_user_conversation_history(self, user_id: int, guild_id: int) -> List[Dict]:
        """从数据库获取用户的对话历史"""
        context = await chat_db_manager.get_ai_conversation_context(user_id, guild_id)
        if context and context.get('conversation_history'):
            return context['conversation_history']
        return []

    # --- Refactored Cooldown Logic ---
    def _get_cooldown_status(self, user_id: int, cooldown_type: str) -> tuple[int, int]:
        """获取用户的冷却状态（请求数和限制数），并清理旧的时间戳。"""
        now = datetime.now(timezone.utc)
        rate_limit = app_config.COOLDOWN_RATES.get(cooldown_type, app_config.COOLDOWN_RATES["default"])

        timestamps = [
            ts for ts in self.user_request_timestamps.get(user_id, [])
            if now - ts < timedelta(minutes=1)
        ]
        self.user_request_timestamps[user_id] = timestamps
        return len(timestamps), rate_limit

    async def _check_and_update_cooldown(self, user_id: int, cooldown_type: str = "default") -> bool:
        """检查并更新用户的冷却状态。"""
        current_requests, rate_limit = self._get_cooldown_status(user_id, cooldown_type)

        if current_requests >= rate_limit:
            log.warning(f"用户 {user_id} 触发了 {cooldown_type} 冷却限制。")
            return False
        
        self.user_request_timestamps.setdefault(user_id, []).append(datetime.now(timezone.utc))
        return True

    async def is_user_on_cooldown(self, user_id: int, cooldown_type: str = "default") -> bool:
        """仅检查用户是否处于冷却状态，不更新时间戳。"""
        current_requests, rate_limit = self._get_cooldown_status(user_id, cooldown_type)
        return current_requests >= rate_limit

    # --- Static Helper Methods for Serialization ---
    @staticmethod
    def _serialize_for_logging(obj):
        """自定义序列化函数，用于截断长文本以进行日志记录。"""
        if isinstance(obj, dict):
            return {key: GeminiService._serialize_for_logging(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [GeminiService._serialize_for_logging(item) for item in obj]
        elif isinstance(obj, str) and len(obj) > 200:
            return obj[:200] + "..."
        elif isinstance(obj, Image.Image):
            return f"<PIL.Image object: mode={obj.mode}, size={obj.size}>"
        else:
            try:
                json.JSONEncoder().default(obj)
                return obj
            except TypeError:
                return str(obj)

    @staticmethod
    def _serialize_parts_for_error_logging(obj):
        """自定义序列化函数，用于在出现问题时记录请求体。"""
        if isinstance(obj, types.Part):
            if obj.text:
                return {"type": "text", "content": obj.text}
            elif obj.inline_data:
                return {"type": "image", "mime_type": obj.inline_data.mime_type, "data_size": len(obj.inline_data.data)}
        elif isinstance(obj, Image.Image):
            return f"<PIL.Image object: mode={obj.mode}, size={obj.size}>"
        try:
            return json.JSONEncoder().default(obj)
        except TypeError:
            return str(obj)

    # --- Refactored generate_response and its helpers ---
    def _prepare_api_contents(self, conversation: List[Dict]) -> List[types.Content]:
        """将对话历史转换为 API 所需的 Content 对象列表。"""
        processed_contents = []
        for turn in conversation:
            role = turn.get("role")
            parts_data = turn.get("parts", [])
            if not (role and parts_data):
                continue

            processed_parts = []
            for part_item in parts_data:
                if isinstance(part_item, str):
                    processed_parts.append(types.Part(text=part_item))
                elif isinstance(part_item, Image.Image):
                    buffered = io.BytesIO()
                    part_item.save(buffered, format="PNG")
                    img_bytes = buffered.getvalue()
                    processed_parts.append(types.Part(
                        inline_data=types.Blob(mime_type='image/png', data=img_bytes)
                    ))
            
            if processed_parts:
                processed_contents.append(types.Content(role=role, parts=processed_parts))
        return processed_contents

    async def _post_process_response(self, raw_response: str, user_id: int, guild_id: int) -> str:
        """对 AI 的原始回复进行清理和处理。"""
        # 1. Clean various reply prefixes and tags
        reply_prefix_pattern = re.compile(r'^\s*([\[［]【回复|回复}\s*@.*?[\)）\]］])\s*', re.IGNORECASE)
        formatted = reply_prefix_pattern.sub('', raw_response)
        formatted = re.sub(r'<CURRENT_USER_MESSAGE_TO_REPLY.*?>', '', formatted, flags=re.IGNORECASE)
        formatted = regex_service.clean_ai_output(formatted)
        
        # 2. Remove old Discord emoji codes
        discord_emoji_pattern = re.compile(r':\w+:')
        formatted = discord_emoji_pattern.sub('', formatted)

        # 3. Replace custom emoji placeholders
        for pattern, emojis in EMOJI_MAPPINGS:
            if isinstance(emojis, list) and emojis:
                selected_emoji = random.choice(emojis)
                formatted = pattern.sub(selected_emoji, formatted)
            elif isinstance(emojis, str):
                formatted = pattern.sub(emojis, formatted)

        # 4. Handle blacklist marker
        blacklist_marker = "<blacklist>"
        if formatted.endswith(blacklist_marker):
            formatted = formatted[:-len(blacklist_marker)].strip()
            try:
                min_d, max_d = app_config.BLACKLIST_BAN_DURATION_MINUTES
                ban_duration = random.randint(min_d, max_d)
                # 确保使用 UTC 时间，与数据库的 datetime('now') 保持一致
                expires_at = datetime.now(timezone.utc) + timedelta(minutes=ban_duration)
                log.info(f"尝试拉黑用户 {user_id}，时长 {ban_duration} 分钟，计算出的过期时间 (UTC): {expires_at}")
                await chat_db_manager.add_to_blacklist(user_id, guild_id, expires_at)
                log.info(f"用户 {user_id} 因不当请求被拉黑 {ban_duration} 分钟，过期时间: {expires_at}。")
                await affection_service.decrease_affection_on_blacklist(user_id, guild_id)
            except Exception as e:
                log.error(f"拉黑用户 {user_id} 时出错: {e}")
        
        return formatted

    async def generate_response(self, user_id: int, guild_id: int, message: str,
                                  images: Optional[List[Dict]] = None, user_name: str = "用户",
                                  channel_context: Optional[List[Dict]] = None,
                                  world_book_entries: Optional[List[Dict]] = None,
                                  personal_summary: Optional[str] = None,
                                  cooldown_type: str = "default") -> str:
        """生成AI回复（已重构）。"""
        if not await self._check_and_update_cooldown(user_id, cooldown_type):
            return None

        key_obj = None
        try:
            # 1. 从轮换服务获取一个可用密钥
            key_obj = await self.key_rotation_service.acquire_key()
            client = self._create_client_with_key(key_obj.key)
            log.debug(f"为用户 {user_id} 获取到密钥 ...{key_obj.key[-4:]}")

            # 2. 构建完整的对话提示
            affection_status = await affection_service.get_affection_status(user_id, guild_id)
            final_conversation = prompt_service.build_chat_prompt(
                user_name=user_name, message=message, images=images,
                channel_context=channel_context, world_book_entries=world_book_entries,
                affection_status=affection_status, personal_summary=personal_summary
            )
            
            # 3. 准备 API 调用参数
            chat_config = app_config.GEMINI_CHAT_CONFIG.copy()
            thinking_budget = chat_config.pop("thinking_budget", None)
            gen_config = types.GenerateContentConfig(
                **chat_config,
                safety_settings=self.safety_settings
            )
            if thinking_budget is not None:
                gen_config.thinking_config = types.ThinkingConfig(thinking_budget=thinking_budget)
            
            processed_contents = self._prepare_api_contents(final_conversation)
            
            # 4. 执行 API 调用
            # 4. 执行 API 调用
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                self.executor,
                lambda: client.models.generate_content(
                    model=self.model_name,
                    contents=processed_contents,
                    config=gen_config
                )
            )
            
            # 5. 处理响应
            if response.parts:
                raw_ai_response = response.text.strip()
                from src.chat.services.context_service import context_service
                await context_service.update_user_conversation_history(
                    user_id, guild_id, message if message else "", raw_ai_response
                )
                formatted_response = await self._post_process_response(raw_ai_response, user_id, guild_id)
                return formatted_response
            
            elif response.prompt_feedback and response.prompt_feedback.block_reason:
                # --- 增强日志记录 ---
                try:
                    # 尝试序列化整个对话历史和响应以进行调试
                    conversation_for_log = json.dumps(
                        GeminiService._serialize_for_logging(final_conversation),
                        ensure_ascii=False,
                        indent=2
                    )
                    full_response_for_log = str(response)
                    log.warning(
                        f"用户 {user_id} 的请求被安全策略阻止，原因: {response.prompt_feedback.block_reason}\n"
                        f"--- 完整的对话历史 ---\n{conversation_for_log}\n"
                        f"--- 完整的 API 响应 ---\n{full_response_for_log}"
                    )
                except Exception as log_e:
                    log.error(f"序列化被阻止的请求用于日志记录时出错: {log_e}")
                    # 即使序列化失败，也记录基本信息
                    log.warning(f"用户 {user_id} 的请求被安全策略阻止，原因: {response.prompt_feedback.block_reason} (详细内容记录失败)")

                return "抱歉，你的消息似乎触发了安全限制，我无法回复。请换个说法试试？"
            
            else:
                log.warning(f"未能为用户 {user_id} 生成有效回复。")
                return "哎呀，我好像没太明白你的意思呢～可以再说清楚一点吗？✨"

        except NoAvailableKeyError:
            log.error("所有 API 密钥当前都不可用（冷却中或已禁用）。")
            return "抱歉，所有AI通道似乎都已满负荷，请稍后再试。"
        except google_exceptions.ResourceExhausted as e:
            log.error(f"密钥 ...{key_obj.key[-4:]} 遭遇配额错误 (429): {e}")
            # 将此密钥标记为失败，以便进入冷却
            if key_obj:
                await self.key_rotation_service.release_key(key_obj.key, success=False)
                key_obj = None # 确保 finally 块不会再次释放它
            return "类脑娘今天累啦,明天再来找她玩吧～"
        except google_exceptions.PermissionDenied as e:
            log.error(f"密钥 ...{key_obj.key[-4:]} 无效或已被吊销: {e}")
            if key_obj:
                self.key_rotation_service.disable_key(key_obj.key, reason=str(e))
                key_obj = None
            return "抱歉，AI服务遇到一个无效的凭证，正在处理中，请稍后再试。"
        except Exception as e:
            log.error(f"生成AI回复时出现意外错误: {e}", exc_info=True)
            return "抱歉，类脑娘有些晕晕的，请稍后再试～ "
        finally:
            # 6. 确保在使用后释放密钥
            if key_obj:
                await self.key_rotation_service.release_key(key_obj.key, success=True)
                log.debug(f"密钥 ...{key_obj.key[-4:]} 已成功释放。")

    async def generate_embedding(self, text: str, task_type: str = "retrieval_document", title: Optional[str] = None) -> Optional[List[float]]:
        """
        为给定文本生成嵌入向量。
        """
        key_obj = None
        try:
            key_obj = await self.key_rotation_service.acquire_key()
            client = self._create_client_with_key(key_obj.key)
            log.debug(f"为嵌入任务获取到密钥 ...{key_obj.key[-4:]}")

            if not text or not text.strip():
                log.warning(f"generate_embedding 接收到空文本！text: '{text}', task_type: '{task_type}'")
                return None

            loop = asyncio.get_event_loop()
            embed_config = types.EmbedContentConfig(task_type=task_type)
            if title and task_type == "retrieval_document":
                embed_config.title = title

            embedding_result = await loop.run_in_executor(
                self.executor,
                lambda: client.models.embed_content(
                    model="gemini-embedding-001",
                    contents=[types.Part(text=text)],
                    config=embed_config
                )
            )
            
            if embedding_result and embedding_result.embeddings:
                return embedding_result.embeddings[0].values
            return None

        except NoAvailableKeyError:
            log.error("所有 API 密钥当前都不可用，无法生成嵌入。")
            return None
        except google_exceptions.ResourceExhausted as e:
            log.error(f"密钥 ...{key_obj.key[-4:]} 在生成嵌入时遭遇配额错误: {e}")
            if key_obj:
                await self.key_rotation_service.release_key(key_obj.key, success=False)
                key_obj = None
            return None
        except google_exceptions.PermissionDenied as e:
            log.error(f"密钥 ...{key_obj.key[-4:]} 无效或已被吊销: {e}")
            if key_obj:
                self.key_rotation_service.disable_key(key_obj.key, reason=str(e))
                key_obj = None
            return None
        except Exception as e:
            log.error(f"生成嵌入时出现意外错误: {e}", exc_info=True)
            return None
        finally:
            if key_obj:
                await self.key_rotation_service.release_key(key_obj.key, success=True)

    async def generate_text(self, prompt: str, temperature: float = None, model_name: Optional[str] = None) -> Optional[str]:
        """
        一个用于简单文本生成的精简方法。
        不涉及对话历史或上下文，仅根据输入提示生成文本。
        非常适合用于如“查询重写”等内部任务。

        Args:
            prompt: 提供给模型的输入提示。
            temperature: 控制生成文本的随机性。如果为 None，则使用 config 中的默认值。
            model_name: 指定要使用的模型。如果为 None，则使用默认的聊天模型。

        Returns:
            生成的文本字符串，如果失败则返回 None。
        """
        key_obj = None
        try:
            key_obj = await self.key_rotation_service.acquire_key()
            client = self._create_client_with_key(key_obj.key)
            log.debug(f"为 generate_text 任务获取到密钥 ...{key_obj.key[-4:]}")

            loop = asyncio.get_event_loop()
            gen_config_params = app_config.GEMINI_TEXT_GEN_CONFIG.copy()
            if temperature is not None:
                gen_config_params["temperature"] = temperature
            gen_config = types.GenerateContentConfig(
                **gen_config_params,
                safety_settings=self.safety_settings
            )
            final_model_name = model_name or self.model_name

            response = await loop.run_in_executor(
                self.executor,
                lambda: client.models.generate_content(
                    model=final_model_name,
                    contents=[prompt],
                    config=gen_config
                )
            )

            if response.parts:
                return response.text.strip()
            return None

        except NoAvailableKeyError:
            log.error("所有 API 密钥当前都不可用，无法生成文本。")
            return None
        except google_exceptions.ResourceExhausted as e:
            log.error(f"密钥 ...{key_obj.key[-4:]} 在 generate_text 时遭遇配额错误: {e}")
            if key_obj:
                await self.key_rotation_service.release_key(key_obj.key, success=False)
                key_obj = None
            return None
        except google_exceptions.PermissionDenied as e:
            log.error(f"密钥 ...{key_obj.key[-4:]} 无效或已被吊销: {e}")
            if key_obj:
                self.key_rotation_service.disable_key(key_obj.key, reason=str(e))
                key_obj = None
            return None
        except Exception as e:
            log.error(f"generate_text 时出现意外错误: {e}", exc_info=True)
            return None
        finally:
            if key_obj:
                await self.key_rotation_service.release_key(key_obj.key, success=True)

    async def generate_simple_response(self, prompt: str, generation_config: Dict) -> Optional[str]:
        """
        一个用于单次、非对话式文本生成的方法，允许传入完整的生成配置。
        非常适合用于如“礼物回应”、“投喂”等需要自定义生成参数的一次性任务。

        Args:
            prompt: 提供给模型的完整输入提示。
            generation_config: 一个包含生成参数的字典 (e.g., temperature, max_output_tokens).

        Returns:
            生成的文本字符串，如果失败则返回 None。
        """
        key_obj = None
        try:
            key_obj = await self.key_rotation_service.acquire_key()
            client = self._create_client_with_key(key_obj.key)
            log.debug(f"为 generate_simple_response 任务获取到密钥 ...{key_obj.key[-4:]}")

            loop = asyncio.get_event_loop()
            gen_config = types.GenerateContentConfig(
                **generation_config,
                safety_settings=self.safety_settings
            )
            final_model_name = self.model_name

            response = await loop.run_in_executor(
                self.executor,
                lambda: client.models.generate_content(
                    model=final_model_name,
                    contents=[prompt],
                    config=gen_config
                )
            )

            if response.parts:
                return response.text.strip()
            
            log.warning(f"generate_simple_response 未能生成有效内容。API 响应: {response}")
            if response.prompt_feedback and response.prompt_feedback.block_reason:
                log.warning(f"请求可能被安全策略阻止，原因: {response.prompt_feedback.block_reason}")
            
            return None

        except NoAvailableKeyError:
            log.error("所有 API 密钥当前都不可用，无法生成文本。")
            return None
        except google_exceptions.ResourceExhausted as e:
            log.error(f"密钥 ...{key_obj.key[-4:]} 在 generate_simple_response 时遭遇配额错误: {e}")
            if key_obj:
                await self.key_rotation_service.release_key(key_obj.key, success=False)
                key_obj = None
            return None
        except google_exceptions.PermissionDenied as e:
            log.error(f"密钥 ...{key_obj.key[-4:]} 无效或已被吊销: {e}")
            if key_obj:
                self.key_rotation_service.disable_key(key_obj.key, reason=str(e))
                key_obj = None
            return None
        except Exception as e:
            log.error(f"generate_simple_response 时出现意外错误: {e}", exc_info=True)
            return None
        finally:
            if key_obj:
                await self.key_rotation_service.release_key(key_obj.key, success=True)

    async def summarize_for_rag(self, latest_query: str, user_name: str, conversation_history: Optional[List[Dict[str, any]]] = None) -> str:
        """
        根据用户的最新发言和可选的对话历史，生成一个用于RAG搜索的独立查询。

        Args:
            latest_query: 用户当前发送的最新消息。
            user_name: 提问用户的名字。
            conversation_history: (可选) 包含多轮对话的列表。

        Returns:
            一个精炼后的、适合向量检索的查询字符串。
        """
        if not latest_query:
            log.info("RAG summarization called with no latest_query.")
            return ""

        prompt = prompt_service.build_rag_summary_prompt(latest_query, user_name, conversation_history)
        summarized_query = await self.generate_text(
            prompt,
            temperature=0.0,
            model_name=app_config.QUERY_REWRITING_MODEL
        )

        if not summarized_query:
            log.info("RAG查询总结失败，将直接使用用户的原始查询。")
            return latest_query.strip()

        return summarized_query.strip().strip('"')

    async def clear_user_context(self, user_id: int, guild_id: int):
        """清除指定用户的对话上下文"""
        await chat_db_manager.clear_ai_conversation_context(user_id, guild_id)
        log.info(f"已清除用户 {user_id} 在服务器 {guild_id} 的对话上下文")
    
    def is_available(self) -> bool:
        """检查AI服务是否可用"""
        return self.key_rotation_service is not None

    async def generate_text_with_image(self, prompt: str, image_bytes: bytes, mime_type: str) -> Optional[str]:
        """
        一个用于简单图文生成的精简方法。
        不涉及对话历史或上下文，仅根据输入提示和图片生成文本。
        非常适合用于如“投喂”等一次性功能。

        Args:
            prompt: 提供给模型的输入提示。
            image_bytes: 图片的字节数据。
            mime_type: 图片的 MIME 类型 (e.g., 'image/jpeg', 'image/png').

        Returns:
            生成的文本字符串，如果失败则返回 None。
        """
        key_obj = None
        try:
            key_obj = await self.key_rotation_service.acquire_key()
            client = self._create_client_with_key(key_obj.key)
            log.debug(f"为 generate_text_with_image 任务获取到密钥 ...{key_obj.key[-4:]}")

            loop = asyncio.get_event_loop()
            request_contents = [
                prompt,
                types.Part(inline_data=types.Blob(mime_type=mime_type, data=image_bytes))
            ]
            gen_config = types.GenerateContentConfig(
                **app_config.GEMINI_VISION_GEN_CONFIG,
                safety_settings=self.safety_settings
            )

            response = await loop.run_in_executor(
                self.executor,
                lambda: client.models.generate_content(
                    model=self.model_name,
                    contents=request_contents,
                    config=gen_config
                )
            )

            if response.parts:
                return response.text.strip()
            elif response.prompt_feedback and response.prompt_feedback.block_reason:
                log.warning(f"图文生成请求被安全策略阻止: {response.prompt_feedback.block_reason}")
                return "这张图片似乎触发了我的安全警报，我没法评价它呢。换一张试试看？"
            
            log.warning(f"未能为图文生成有效回复。Response: {response}")
            return "我好像没看懂这张图里是什么，可以换一张或者稍后再试试吗？"

        except NoAvailableKeyError:
            log.error("所有 API 密钥当前都不可用，无法进行图文生成。")
            return "抱歉，所有AI通道似乎都已满负荷，请稍后再试。"
        except google_exceptions.ResourceExhausted as e:
            log.error(f"密钥 ...{key_obj.key[-4:]} 在图文生成时遭遇配额错误: {e}")
            if key_obj:
                await self.key_rotation_service.release_key(key_obj.key, success=False)
                key_obj = None
            return None
        except google_exceptions.PermissionDenied as e:
            log.error(f"密钥 ...{key_obj.key[-4:]} 无效或已被吊销: {e}")
            if key_obj:
                self.key_rotation_service.disable_key(key_obj.key, reason=str(e))
                key_obj = None
            return None
        except Exception as e:
            log.error(f"图文生成时出现意外错误: {e}", exc_info=True)
            return "啊呀，处理图片的时候我好像有点晕...稍后再试试可以吗？"
        finally:
            if key_obj:
                await self.key_rotation_service.release_key(key_obj.key, success=True)

# 全局实例
gemini_service = GeminiService()
