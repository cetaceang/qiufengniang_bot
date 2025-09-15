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

# 导入数据库管理器和提示词配置
from src.chat.utils.database import chat_db_manager
from src.chat.config import chat_config as app_config
from src.chat.config.emoji_config import EMOJI_MAPPINGS
from src.chat.features.affection.service.affection_service import affection_service
from src.chat.services.regex_service import regex_service
from src.chat.services.prompt_service import prompt_service
 
log = logging.getLogger(__name__)

class GeminiService:
    """Gemini AI 服务类，使用数据库存储用户对话上下文"""

    def __init__(self):
        # 支持多个API密钥轮询，用逗号分隔
        api_keys_str = os.getenv("GEMINI_API_KEYS", "")
        # 支持多行和逗号分隔的密钥
        self.api_keys = [key.strip() for line in api_keys_str.splitlines() for key in line.split(',') if key.strip()]
        self.current_key_index = 0
        self.model_name = app_config.GEMINI_MODEL
        self.clients = {}  # 存储每个API密钥对应的客户端
        self.executor = ThreadPoolExecutor(max_workers=10)  # 增加工作线程数
        self.user_request_timestamps: Dict[int, List[datetime]] = {}  # 用户请求时间戳，用于冷却
        self.initialize_clients()

    def initialize_clients(self):
        """初始化所有Gemini客户端（支持多个API密钥）"""
        if not self.api_keys:
            log.warning("GEMINI_API_KEYS 未设置，AI功能将不可用")
            return
        
        for i, api_key in enumerate(self.api_keys):
            try:
                # 为每个API密钥创建独立的客户端
                client = genai.Client(api_key=api_key)
                self.clients[api_key] = client
                log.info(f"Gemini客户端 (密钥 #{i+1}) 初始化成功")
            except Exception as e:
                log.error(f"初始化Gemini客户端 (密钥 #{i+1}) 失败: {e}")
        
        if not self.clients:
            log.error("所有API密钥初始化失败，AI功能将不可用")

    async def get_user_conversation_history(self, user_id: int, guild_id: int) -> List[Dict]:
        """从数据库获取用户的对话历史"""
        context = await chat_db_manager.get_ai_conversation_context(user_id, guild_id)
        if context and context.get('conversation_history'):
            return context['conversation_history']
        return []

    def get_next_client(self):
        """获取下一个可用的客户端（轮询模式）"""
        if not self.clients:
            return None
        
        api_keys = list(self.clients.keys())
        selected_key = api_keys[self.current_key_index]
        self.current_key_index = (self.current_key_index + 1) % len(api_keys)
        
        return self.clients[selected_key]

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
        if not self.clients:
            return "抱歉，类脑娘暂时休息啦，请稍后再试～ "

        if not await self._check_and_update_cooldown(user_id, cooldown_type):
            return None

        try:
            # 1. Build the complete conversation prompt
            affection_status = await affection_service.get_affection_status(user_id, guild_id)
            final_conversation = prompt_service.build_chat_prompt(
                user_name=user_name, message=message, images=images,
                channel_context=channel_context, world_book_entries=world_book_entries,
                affection_status=affection_status, personal_summary=personal_summary
            )
            
            # 记录最终发送给 API 的完整上下文
            try:
                # 使用 _serialize_parts_for_error_logging 来避免截断长文本
                logged_payload = json.dumps(final_conversation, indent=2, ensure_ascii=False, default=self._serialize_parts_for_error_logging)
                log.debug(f"--- Final Context to Gemini API (User: {user_id}) ---\n"
                         f"{logged_payload}\n"
                         f"----------------------------------------------------")
            except Exception as log_e:
                log.error(f"序列化上下文用于日志记录时失败: {log_e}")

            # 2. Prepare API call parameters
            chat_config = app_config.GEMINI_CHAT_CONFIG.copy()
            thinking_budget = chat_config.pop("thinking_budget", None)

            gen_config = types.GenerateContentConfig(**chat_config)
            if thinking_budget is not None:
                gen_config.thinking_config = types.ThinkingConfig(thinking_budget=thinking_budget)
            

            processed_contents = self._prepare_api_contents(final_conversation)
            
            # 3. Loop through API keys and attempt to get a response
            for _ in range(len(self.clients)):
                client = self.get_next_client()
                if not client:
                    continue

                log.debug(f"正在使用 API 密钥 #{self.current_key_index} 为用户 {user_id} 生成回复...")

                try:
                    loop = asyncio.get_event_loop()
                    response = await loop.run_in_executor(
                        self.executor,
                        lambda: client.models.generate_content(
                            model=self.model_name,
                            contents=processed_contents,
                            config=gen_config
                        )
                    )
                    

                    if response.parts:
                        raw_ai_response = response.text.strip()
                        
                        from src.chat.services.context_service import context_service
                        await context_service.update_user_conversation_history(
                            user_id, guild_id, message if message else "", raw_ai_response
                        )
                        
                        formatted_response = await self._post_process_response(raw_ai_response, user_id, guild_id)
                        # log.info(f"即将为用户 {user_id} 返回AI回复: {formatted_response}") # 这条日志将移至 chat_service
                        return formatted_response
                    
                    elif response.prompt_feedback and response.prompt_feedback.block_reason:
                        log.warning(f"用户 {user_id} 的请求被 API 密钥 #{self.current_key_index} 的安全策略阻止，原因: {response.prompt_feedback.block_reason}")
                        return "抱歉，你的消息似乎触发了安全限制，我无法回复。请换个说法试试？"
                    
                    else:
                        log.warning(f"API 密钥 #{self.current_key_index} 未能为用户 {user_id} 生成有效回复。将尝试下一个密钥。")
                        try:
                            problematic_body = json.dumps(final_conversation, indent=2, ensure_ascii=False, default=self._serialize_parts_for_error_logging)
                            log.warning(f"导致空回复的请求体详情:\n{problematic_body}")
                        except Exception as e:
                            log.error(f"序列化问题请求体用于日志记录时失败: {e}")

                except (google_exceptions.InternalServerError, google_exceptions.ServiceUnavailable, google_exceptions.ResourceExhausted) as e:
                    log.warning(f"API 密钥 #{self.current_key_index} 遇到可重试的API错误: {e}. 将尝试下一个密钥。")
                    continue
            
            log.error(f"所有 API 密钥都未能为用户 {user_id} 生成有效回复。")
            return "哎呀，我好像没太明白你的意思呢～可以再说清楚一点吗？✨"
                
        except Exception as e:
            log.error(f"生成AI回复时出现意外错误: {e}", exc_info=True)
            error_msg = str(e).lower()
            if "429" in error_msg or "quota" in error_msg or "limit" in error_msg:
                log.info(f"用户 {user_id} 触发了 429/配额限制错误: {e}")
                return "类脑娘今天累啦,明天再来找她玩吧～"
            elif "network" in error_msg or "timeout" in error_msg or "connect" in error_msg:
                return "类脑娘的...网络...似乎有些不稳定，请稍后...再试～"
            elif "image" in error_msg or "mime" in error_msg:
                return "呜哇,我无法识别这张图片呢，请尝试其他图片～"
            elif "400" in error_msg or "invalid" in error_msg:
                return "类脑娘收到了看不懂的东西，请检查消息内容～"
            else:
                return "抱歉，类脑娘有些晕晕的，请稍后再试～ "

    async def generate_embedding(self, text: str, task_type: str = "retrieval_document", title: Optional[str] = None) -> Optional[List[float]]:
        """
        为给定文本生成嵌入向量。

        Args:
            text: 需要进行嵌入的文本。
            task_type: 任务类型 ('retrieval_query', 'retrieval_document', 'semantic_similarity', etc.)
            title: 可选的文本标题，仅在 task_type 为 'retrieval_document' 时使用。

        Returns:
            代表文本的浮点数列表（嵌入向量），如果失败则返回 None。
        """
        if not self.clients:
            log.error("没有可用的 Gemini 客户端，无法生成嵌入。")
            return None

        for i in range(len(self.clients)):
            client = self.get_next_client()
            if not client:
                continue

            log.debug(f"正在使用 API 密钥 #{self.current_key_index} 为文本生成嵌入...")
            
            try:
                loop = asyncio.get_event_loop()
                
                embed_config = types.EmbedContentConfig(task_type=task_type)
                if title and task_type == "retrieval_document":
                    embed_config.title = title
                    log.debug(f"      -> 使用标题 '{title}' 进行文档嵌入。")

                embedding_result = await loop.run_in_executor(
                    self.executor,
                    lambda: client.models.embed_content(
                        model="gemini-embedding-001",
                        contents=[text],
                        config=embed_config
                    )
                )
                
                if embedding_result and embedding_result.embeddings:
                    log.debug(f"成功为文本生成嵌入向量。")
                    return embedding_result.embeddings[0].values
                else:
                    log.warning(f"API 密钥 #{self.current_key_index} 未能生成有效的嵌入。")

            except (google_exceptions.InternalServerError, google_exceptions.ServiceUnavailable, google_exceptions.ResourceExhausted) as e:
                log.warning(f"API 密钥 #{self.current_key_index} 遇到可重试的API错误: {e}. 将尝试下一个密钥。")
                continue
            except Exception as e:
                log.error(f"使用 API 密钥 #{self.current_key_index} 生成嵌入时出现意外错误: {e}", exc_info=True)
                break
        
        log.error("所有 API 密钥都未能生成嵌入。")
        return None

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
        if not self.clients:
            log.error("没有可用的 Gemini 客户端，无法生成文本。")
            return None

        for i in range(len(self.clients)):
            client = self.get_next_client()
            if not client:
                continue

            log.debug(f"正在使用 API 密钥 #{self.current_key_index} (generate_text) 生成文本...")
            try:
                loop = asyncio.get_event_loop()
                
                gen_config_params = app_config.GEMINI_TEXT_GEN_CONFIG.copy()
                if temperature is not None:
                    gen_config_params["temperature"] = temperature
                
                gen_config = types.GenerateContentConfig(**gen_config_params)

                final_model_name = model_name or self.model_name
                log.debug(f"generate_text 将使用模型: {final_model_name}")

                response = await loop.run_in_executor(
                    self.executor,
                    lambda: client.models.generate_content(
                        model=final_model_name,
                        contents=[prompt],
                        config=gen_config
                    )
                )

                if response.parts:
                    rewritten_query = response.text.strip()
                    log.debug(f"成功生成文本 (generate_text): \"{rewritten_query}\"")
                    return rewritten_query
                else:
                    log.warning(f"API 密钥 #{self.current_key_index} (generate_text) 未能生成有效文本。")

            except Exception as e:
                log.error(f"使用 API 密钥 #{self.current_key_index} (generate_text) 时出现意外错误: {e}", exc_info=True)
                continue
        
        log.error("所有 API 密钥都未能成功执行 generate_text。")
        return None

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
        return len(self.clients) > 0

# 全局实例
gemini_service = GeminiService()
