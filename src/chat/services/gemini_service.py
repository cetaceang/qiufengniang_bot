# -*- coding: utf-8 -*-

import os
import logging
from typing import Optional, Dict, List, Callable, Any
import asyncio
from functools import wraps
from concurrent.futures import ThreadPoolExecutor
import json
from datetime import datetime, timezone, timedelta
import re
import random

from PIL import Image
import io

# 导入新库
from google import genai
from google.genai import types
from google.genai import errors as genai_errors

# 导入数据库管理器和提示词配置
from src.chat.utils.database import chat_db_manager
from src.chat.config import chat_config as app_config
from src.chat.config.emoji_config import EMOJI_MAPPINGS, FACTION_EMOJI_MAPPINGS
from src.chat.services.event_service import event_service
from src.chat.features.affection.service.affection_service import affection_service
from src.chat.services.regex_service import regex_service
from src.chat.services.prompt_service import prompt_service
from src.chat.services.key_rotation_service import (
    KeyRotationService,
    NoAvailableKeyError,
)
from src.chat.features.tools.tool_registry import tool_registry
from src.chat.features.tools.services.tool_service import ToolService

log = logging.getLogger(__name__)

# --- 设置专门用于记录无效 API 密钥的 logger ---
# 确保 data 目录存在
if not os.path.exists("data"):
    os.makedirs("data")

# 创建一个新的 logger 实例
invalid_key_logger = logging.getLogger("invalid_api_keys")
invalid_key_logger.setLevel(logging.ERROR)

# 创建文件处理器，将日志写入到 data/invalid_api_keys.log
# 使用 a 模式表示追加写入
fh = logging.FileHandler("data/invalid_api_keys.log", mode="a", encoding="utf-8")
fh.setLevel(logging.ERROR)

# 创建格式化器并设置
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
fh.setFormatter(formatter)

# 为 logger 添加处理器
# 防止重复添加处理器
if not invalid_key_logger.handlers:
    invalid_key_logger.addHandler(fh)


class GeminiService:
    """Gemini AI 服务类，使用数据库存储用户对话上下文"""

    def __init__(self):
        self.bot = None  # 用于存储 Discord Bot 实例

        # --- 密钥轮换服务 ---
        google_api_keys_str = os.getenv("GOOGLE_API_KEYS_LIST", "")
        if not google_api_keys_str:
            log.error("GOOGLE_API_KEYS_LIST 环境变量未设置！服务将无法运行。")
            # 在这种严重配置错误下，抛出异常以阻止应用启动
            raise ValueError("GOOGLE_API_KEYS_LIST is not set.")

        # 先移除整个字符串两端的空格和引号，以支持 "key1,key2" 格式
        processed_keys_str = google_api_keys_str.strip().strip('"')
        api_keys = [key.strip() for key in processed_keys_str.split(",") if key.strip()]
        self.key_rotation_service = KeyRotationService(api_keys)
        log.info(
            f"GeminiService 初始化并由 KeyRotationService 管理 {len(api_keys)} 个密钥。"
        )

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

        # --- 工具配置 ---
        self.tool_service = ToolService()  # 实例化工具服务
        # 通过导入工具模块（例如 get_user_avatar），工具会自动注册。
        self.tools = tool_registry.get_all_tools_schema()
        if self.tools:
            log.info(
                f"已加载 {len(self.tools)} 个工具: {[tool['name'] for tool in self.tools]}"
            )
        else:
            log.info("未从工具注册中心加载任何工具。")

    def set_bot(self, bot):
        """注入 Discord Bot 实例。"""
        self.bot = bot
        log.info("Discord Bot 实例已成功注入 GeminiService。")

    def _create_client_with_key(self, api_key: str):
        """使用给定的 API 密钥动态创建一个 Gemini 客户端实例。"""
        base_url = os.getenv("GEMINI_API_BASE_URL")
        if base_url:
            log.info(f"使用自定义 Gemini API 端点: {base_url}")
            # 根据用户提供的文档，正确的方法是使用 types.HttpOptions
            # Cloudflare Worker 需要 /gemini 后缀，所以我们不移除它
            http_options = types.HttpOptions(base_url=base_url)
            return genai.Client(api_key=api_key, http_options=http_options)
        else:
            log.info("使用默认 Gemini API 端点。")
            return genai.Client(api_key=api_key)

    async def get_user_conversation_history(
        self, user_id: int, guild_id: int
    ) -> List[Dict]:
        """从数据库获取用户的对话历史"""
        context = await chat_db_manager.get_ai_conversation_context(user_id, guild_id)
        if context and context.get("conversation_history"):
            return context["conversation_history"]
        return []

    # --- Refactored Cooldown Logic ---

    # --- Static Helper Methods for Serialization ---
    @staticmethod
    def _serialize_for_logging(obj):
        """自定义序列化函数，用于截断长文本以进行日志记录。"""
        if isinstance(obj, dict):
            return {
                key: GeminiService._serialize_for_logging(value)
                for key, value in obj.items()
            }
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
                return {
                    "type": "image",
                    "mime_type": obj.inline_data.mime_type,
                    "data_size": len(obj.inline_data.data),
                }
        elif isinstance(obj, Image.Image):
            return f"<PIL.Image object: mode={obj.mode}, size={obj.size}>"
        try:
            return json.JSONEncoder().default(obj)
        except TypeError:
            return str(obj)

    @staticmethod
    def _serialize_parts_for_logging_full(content: types.Content):
        """自定义序列化函数，用于完整记录 Content 对象。"""
        serialized_parts = []
        for part in content.parts:
            if part.text:
                serialized_parts.append({"type": "text", "content": part.text})
            elif part.inline_data:
                serialized_parts.append(
                    {
                        "type": "image",
                        "mime_type": part.inline_data.mime_type,
                        "data_size": len(part.inline_data.data),
                        "data_preview": part.inline_data.data[:50].hex()
                        + "...",  # 记录数据前50字节的十六进制预览
                    }
                )
            elif part.file_data:
                serialized_parts.append(
                    {
                        "type": "file",
                        "mime_type": part.file_data.mime_type,
                        "file_uri": part.file_data.file_uri,
                    }
                )
            else:
                serialized_parts.append({"type": "unknown_part", "content": str(part)})
        return {"role": content.role, "parts": serialized_parts}

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
                    processed_parts.append(
                        types.Part(
                            inline_data=types.Blob(
                                mime_type="image/png", data=img_bytes
                            )
                        )
                    )

            if processed_parts:
                processed_contents.append(
                    types.Content(role=role, parts=processed_parts)
                )
        return processed_contents

    async def _post_process_response(
        self, raw_response: str, user_id: int, guild_id: int
    ) -> str:
        """对 AI 的原始回复进行清理和处理。"""
        # 1. Clean various reply prefixes and tags
        reply_prefix_pattern = re.compile(
            r"^\s*([\[［]【回复|回复}\s*@.*?[\)）\]］])\s*", re.IGNORECASE
        )
        formatted = reply_prefix_pattern.sub("", raw_response)
        formatted = re.sub(
            r"<CURRENT_USER_MESSAGE_TO_REPLY.*?>", "", formatted, flags=re.IGNORECASE
        )
        formatted = regex_service.clean_ai_output(formatted)

        # 2. Remove old Discord emoji codes
        discord_emoji_pattern = re.compile(r":\w+:")
        formatted = discord_emoji_pattern.sub("", formatted)

        # 3. Replace custom emoji placeholders
        active_event = event_service.get_active_event()
        selected_faction = event_service.get_selected_faction()

        emoji_map_to_use = EMOJI_MAPPINGS  # Default to global map

        if active_event and selected_faction:
            event_id = active_event.get("event_id")
            faction_map = FACTION_EMOJI_MAPPINGS.get(event_id, {}).get(selected_faction)
            if faction_map:
                log.info(
                    f"使用事件 '{event_id}' 派系 '{selected_faction}' 的专属表情包。"
                )
                emoji_map_to_use = faction_map
            else:
                log.info(
                    f"未找到派系 '{selected_faction}' 的专属表情包，使用全局表情包。"
                )
        else:
            log.info("未使用任何派系表情包，使用全局表情包。")

        for pattern, emojis in emoji_map_to_use:
            if isinstance(emojis, list) and emojis:
                selected_emoji = random.choice(emojis)
                formatted = pattern.sub(selected_emoji, formatted)
            elif isinstance(emojis, str):
                formatted = pattern.sub(emojis, formatted)

        # 4. Handle warning marker
        warning_marker = "<warn>"
        if formatted.endswith(warning_marker):
            formatted = formatted[: -len(warning_marker)].strip()
            try:
                min_d, max_d = app_config.BLACKLIST_BAN_DURATION_MINUTES
                ban_duration = random.randint(min_d, max_d)
                expires_at = datetime.now(timezone.utc) + timedelta(
                    minutes=ban_duration
                )

                log.info(f"用户 {user_id} 在服务器 {guild_id} 收到一次警告。")

                was_blacklisted = (
                    await chat_db_manager.record_warning_and_check_blacklist(
                        user_id, guild_id, expires_at
                    )
                )

                if was_blacklisted:
                    log.info(
                        f"用户 {user_id} 因累计3次警告被自动拉黑 {ban_duration} 分钟，过期时间: {expires_at}。"
                    )
                    await affection_service.decrease_affection_on_blacklist(
                        user_id, guild_id
                    )
                # 如果只是警告而未拉黑，也可以考虑在这里进行轻微的好感度惩罚，但根据当前需求，我们只在拉黑时操作。

            except Exception as e:
                log.error(f"处理用户 {user_id} 的警告时出错: {e}")

        return formatted

    def _handle_safety_ratings(
        self, response: types.GenerateContentResponse, key: str
    ) -> int:
        """检查响应的安全评分并返回相应的惩罚值。"""
        total_penalty = 0
        if not response.candidates:
            return 0

        candidate = response.candidates[0]
        if candidate.safety_ratings:
            for rating in candidate.safety_ratings:
                # 将枚举值转换为字符串键
                category_name = rating.category.name.replace("HARM_CATEGORY_", "")
                severity_name = rating.probability.name

                penalty = self.SAFETY_PENALTY_MAP.get(severity_name, 0)
                if penalty > 0:
                    log.warning(
                        f"密钥 ...{key[-4:]} 收到安全警告。类别: {category_name}, 严重性: {severity_name}, 惩罚: {penalty}"
                    )
                    total_penalty += penalty
        return total_penalty

    def _api_key_handler(func: Callable) -> Callable:
        """
        一个装饰器，用于优雅地处理 API 密钥的获取、释放和重试逻辑。
        实现了两层重试：
        1. 外层循环：持续获取可用密钥，如果所有密钥都在冷却，则会等待。
        2. 内层循环：对获取到的单个密钥，在遇到可重试错误时，会根据配置进行多次尝试。
        """

        @wraps(func)
        async def wrapper(self: "GeminiService", *args, **kwargs):
            last_exception = None

            while True:
                key_obj = None
                try:
                    key_obj = await self.key_rotation_service.acquire_key()
                    client = self._create_client_with_key(key_obj.key)

                    failure_penalty = 25  # 默认的失败惩罚
                    key_should_be_cooled_down = False
                    key_is_invalid = False

                    max_attempts = app_config.API_RETRY_CONFIG["MAX_ATTEMPTS_PER_KEY"]
                    for attempt in range(max_attempts):
                        try:
                            log.info(
                                f"使用密钥 ...{key_obj.key[-4:]} (尝试 {attempt + 1}/{max_attempts}) 调用 {func.__name__}"
                            )

                            result = await func(self, *args, client=client, **kwargs)

                            safety_penalty = 0
                            is_blocked_by_safety = False
                            if isinstance(result, types.GenerateContentResponse):
                                safety_penalty = self._handle_safety_ratings(
                                    result, key_obj.key
                                )
                                if (
                                    not result.parts
                                    and result.prompt_feedback
                                    and result.prompt_feedback.block_reason
                                ):
                                    is_blocked_by_safety = True

                            if is_blocked_by_safety:
                                log.warning(
                                    f"密钥 ...{key_obj.key[-4:]} 因安全策略被阻止 (原因: {result.prompt_feedback.block_reason})。将进入冷却且不扣分。"
                                )
                                failure_penalty = 0  # 明确设置为0，不扣分
                                key_should_be_cooled_down = True
                                break

                            await self.key_rotation_service.release_key(
                                key_obj.key, success=True, safety_penalty=safety_penalty
                            )
                            return result

                        except (
                            genai_errors.ClientError,
                            genai_errors.ServerError,
                        ) as e:
                            last_exception = e
                            error_str = str(e)
                            match = re.match(r"(\d{3})", error_str)
                            status_code = int(match.group(1)) if match else None

                            is_retryable = status_code in [429, 503]
                            if (
                                not is_retryable
                                and isinstance(e, genai_errors.ServerError)
                                and "503" in error_str
                            ):
                                is_retryable = True
                                status_code = 503

                            if is_retryable:
                                log.warning(
                                    f"密钥 ...{key_obj.key[-4:]} 遇到可重试错误 (状态码: {status_code})。"
                                )
                                if attempt < max_attempts - 1:
                                    delay = app_config.API_RETRY_CONFIG[
                                        "RETRY_DELAY_SECONDS"
                                    ]
                                    log.info(f"等待 {delay} 秒后重试。")
                                    await asyncio.sleep(delay)
                                else:
                                    log.warning(
                                        f"密钥 ...{key_obj.key[-4:]} 的所有 {max_attempts} 次重试均失败。将进入冷却。"
                                    )
                                    # --- 渐进式惩罚逻辑 ---
                                    base_penalty = 10
                                    consecutive_failures = (
                                        key_obj.consecutive_failures + 1
                                    )  # +1 是因为本次失败也要计算在内
                                    failure_penalty = (
                                        base_penalty * consecutive_failures
                                    )
                                    log.warning(
                                        f"密钥 ...{key_obj.key[-4:]} 已连续失败 {consecutive_failures} 次。"
                                        f"本次惩罚分值: {failure_penalty}"
                                    )
                                    key_should_be_cooled_down = True

                            elif status_code == 403 or (
                                status_code == 400
                                and "API_KEY_INVALID" in error_str.upper()
                            ):
                                log.error(
                                    f"密钥 ...{key_obj.key[-4:]} 无效 (状态码: {status_code})。将施加毁灭性惩罚。"
                                )
                                failure_penalty = 101  # 毁灭性惩罚
                                key_should_be_cooled_down = True
                                break  # 直接跳出重试循环

                            else:
                                log.error(
                                    f"使用密钥 ...{key_obj.key[-4:]} 时发生意外的致命API错误 (状态码: {status_code}): {e}",
                                    exc_info=True,
                                )
                                if isinstance(e, genai_errors.ServerError):
                                    # 对于服务器错误，也采用渐进式惩罚
                                    base_penalty = 15  # 服务器错误的基础惩罚可以稍高
                                    consecutive_failures = (
                                        key_obj.consecutive_failures + 1
                                    )
                                    failure_penalty = (
                                        base_penalty * consecutive_failures
                                    )
                                    log.warning(
                                        f"密钥 ...{key_obj.key[-4:]} 遭遇服务器错误，已连续失败 {consecutive_failures} 次。"
                                        f"本次惩罚分值: {failure_penalty}"
                                    )
                                    key_should_be_cooled_down = True
                                    break
                                else:
                                    await self.key_rotation_service.release_key(
                                        key_obj.key, success=True
                                    )
                                    return "抱歉，AI服务遇到了一个意料之外的错误，请稍后再试。"

                        except Exception as e:
                            log.error(
                                f"使用密钥 ...{key_obj.key[-4:]} 时发生未知错误: {e}",
                                exc_info=True,
                            )
                            await self.key_rotation_service.release_key(
                                key_obj.key, success=True
                            )
                            if func.__name__ == "generate_embedding":
                                return None
                            return "呜哇，有点晕嘞，等我休息一会儿 <伤心>"

                    if key_is_invalid:
                        continue

                    if key_should_be_cooled_down:
                        await self.key_rotation_service.release_key(
                            key_obj.key, success=False, failure_penalty=failure_penalty
                        )

                except NoAvailableKeyError:
                    log.error(
                        "所有API密钥均不可用，且 acquire_key 未能成功等待。这是异常情况。"
                    )
                    return "啊啊啊服务器要爆炸啦！现在有点忙不过来，你过一会儿再来找我玩吧！<生气>"

        return wrapper

    @_api_key_handler
    async def generate_response(
        self,
        user_id: int,
        guild_id: int,
        message: str,
        replied_message: Optional[str] = None,
        images: Optional[List[Dict]] = None,
        user_name: str = "用户",
        channel_context: Optional[List[Dict]] = None,
        world_book_entries: Optional[List[Dict]] = None,
        personal_summary: Optional[str] = None,
        affection_status: Optional[Dict[str, Any]] = None,
        user_profile_data: Optional[Dict[str, Any]] = None,
        client: Any = None,
    ) -> str:
        """生成AI回复（已重构）。"""
        # --- 新逻辑：冷却检查已移至装饰器，此处不再需要 ---
        # 装饰器会处理密钥和客户端的创建，这里我们直接使用
        # 注意：装饰器会将 client 作为关键字参数注入
        if not client:
            raise ValueError("装饰器未能提供客户端实例。")

        # 移除外层 try...except，让异常传递给装饰器
        # 1. 构建完整的对话提示
        final_conversation = prompt_service.build_chat_prompt(
            user_name=user_name,
            message=message,
            replied_message=replied_message,
            images=images,
            channel_context=channel_context,
            world_book_entries=world_book_entries,
            affection_status=affection_status,
            personal_summary=personal_summary,
            user_profile_data=user_profile_data,
        )

        # 3. 准备 API 调用参数 (重构以符合文档规范)
        chat_config = app_config.GEMINI_CHAT_CONFIG.copy()
        thinking_budget = chat_config.pop("thinking_budget", None)

        # 3.1. 严格按照文档，预先准备好 tools 参数
        tools_for_api = None
        if self.tools:
            tools_for_api = [types.Tool(function_declarations=self.tools)]

            log.info(
                f"--- 发送给 Gemini 的工具定义 ---\n{json.dumps(self.tools, indent=2, ensure_ascii=False)}"
            )

        # 3.2. 构建 GenerateContentConfig 的构造函数参数字典
        gen_config_params = {**chat_config, "safety_settings": self.safety_settings}
        if tools_for_api:
            gen_config_params["tools"] = tools_for_api
            # --- 诊断性修改：强制模型调用工具 ---
            gen_config_params["tool_config"] = types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(
                    mode=types.FunctionCallingConfig.Mode.ANY
                )
            )
            log.info("--- 诊断模式：已强制开启 ANY 模式进行工具调用测试 ---")

        # 3.3. 在初始化时一次性传入所有参数，包括 tools
        gen_config = types.GenerateContentConfig(**gen_config_params)

        if thinking_budget is not None:
            gen_config.thinking_config = types.ThinkingConfig(
                thinking_budget=thinking_budget
            )

        processed_contents = self._prepare_api_contents(final_conversation)

        # 如果开启了 AI 完整上下文日志，则打印到终端
        if app_config.DEBUG_CONFIG["LOG_AI_FULL_CONTEXT"]:
            log.info(f"--- AI 完整上下文日志 (用户 {user_id}) ---")
            log.info(
                json.dumps(
                    [
                        self._serialize_parts_for_logging_full(content)
                        for content in processed_contents
                    ],
                    ensure_ascii=False,
                    indent=2,
                )
            )
            log.info("------------------------------------")

        # 4. 执行 API 调用 (严格遵循文档的异步方式)
        log.info(f"--- 正在为用户 {user_id} 调用 Gemini API (异步修正版) ---")
        log.debug(f"Contents for API: {processed_contents}")
        log.debug(f"Config for API: {gen_config}")

        # 根据文档第690行，异步函数应使用 client.aio.models
        response = await client.aio.models.generate_content(
            model=self.model_name,
            contents=processed_contents,
            config=gen_config,  # 遵循文档示例，使用 config=
        )

        log.info(f"--- 从 Gemini 收到的原始响应 ---\n{response}")

        # --- 函数调用集成逻辑 ---
        # 检查模型的回复是否包含函数调用请求
        # 检查模型的回复是否包含函数调用请求
        # 根据文档，candidates 和 parts 都是列表，需要通过索引 [0] 访问
        if (
            response.candidates
            and len(response.candidates) > 0
            and response.candidates[0].content
            and response.candidates[0].content.parts
            and len(response.candidates[0].content.parts) > 0
            and response.candidates[0].content.parts[0].function_call
        ):
            candidate = response.candidates[0]
            function_call = candidate.content.parts[0].function_call
            log.info(
                f"模型请求调用工具: {function_call.name}，参数: {dict(function_call.args)}"
            )

            # 使用实例化的工具服务执行调用，并传入 bot 实例
            if not self.bot:
                log.error("GeminiService 中缺少 Bot 实例，无法执行需要 Bot 的工具！")
                # 返回一个错误信息给模型，让它知道工具调用失败了
                tool_result_part = types.Part.from_function_response(
                    name=function_call.name,
                    response={
                        "content": {"error": "Internal error: Bot is not available."}
                    },
                )
            else:
                tool_result_part = await self.tool_service.execute_tool_call(
                    tool_call=function_call, bot=self.bot, author_id=message.author.id
                )
            log.info(f"已从 tool_service 收到 Part: {tool_result_part}")

            # 将模型的原始回复（即函数调用本身）和工具执行的结果都追加到对话历史中
            # 这是让模型理解它发起了什么调用以及调用结果是什么的关键步骤
            processed_contents.append(candidate.content)  # 使用正确的 candidate.content
            processed_contents.append(
                types.Content(role="user", parts=[tool_result_part])
            )

            # 将带有工具结果的新对话历史再次发送给模型，以生成最终的自然语言回复
            log.info("已将工具执行结果返回给模型，以进行最终的文本合成。")

            # 第二次调用同样遵循文档的异步方式
            response = await client.aio.models.generate_content(
                model=self.model_name,
                contents=processed_contents,
                config=gen_config,  # 遵循文档示例，使用 config=
            )
            log.info("已收到模型在工具执行后的最终回复。")
        # --- 函数调用集成结束 ---

        # 3. 处理响应
        if response.parts:
            raw_ai_response = response.text.strip()
            from src.chat.services.context_service import context_service

            await context_service.update_user_conversation_history(
                user_id, guild_id, message if message else "", raw_ai_response
            )
            formatted_response = await self._post_process_response(
                raw_ai_response, user_id, guild_id
            )
            return formatted_response

        elif response.prompt_feedback and response.prompt_feedback.block_reason:
            # --- 增强日志记录 ---
            try:
                # 尝试序列化整个对话历史和响应以进行调试
                conversation_for_log = json.dumps(
                    GeminiService._serialize_for_logging(final_conversation),
                    ensure_ascii=False,
                    indent=2,
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
                log.warning(
                    f"用户 {user_id} 的请求被安全策略阻止，原因: {response.prompt_feedback.block_reason} (详细内容记录失败)"
                )

            return "呜啊! 这个太色情啦,我不看我不看"

        else:
            log.warning(f"未能为用户 {user_id} 生成有效回复。")
            return "哎呀，我好像没太明白你的意思呢～可以再说清楚一点吗？✨"

    @_api_key_handler
    async def generate_embedding(
        self,
        text: str,
        task_type: str = "retrieval_document",
        title: Optional[str] = None,
        client: Any = None,
    ) -> Optional[List[float]]:
        """
        为给定文本生成嵌入向量。
        """
        if not client:
            raise ValueError("装饰器未能提供客户端实例。")

        if not text or not text.strip():
            log.warning(
                f"generate_embedding 接收到空文本！text: '{text}', task_type: '{task_type}'"
            )
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
                config=embed_config,
            ),
        )

        if embedding_result and embedding_result.embeddings:
            return embedding_result.embeddings[0].values
        return None

    @_api_key_handler
    async def generate_text(
        self,
        prompt: str,
        temperature: float = None,
        model_name: Optional[str] = None,
        client: Any = None,
    ) -> Optional[str]:
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
        if not client:
            raise ValueError("装饰器未能提供客户端实例。")

        loop = asyncio.get_event_loop()
        gen_config_params = app_config.GEMINI_TEXT_GEN_CONFIG.copy()
        if temperature is not None:
            gen_config_params["temperature"] = temperature
        gen_config = types.GenerateContentConfig(
            **gen_config_params, safety_settings=self.safety_settings
        )
        final_model_name = model_name or self.model_name

        response = await loop.run_in_executor(
            self.executor,
            lambda: client.models.generate_content(
                model=final_model_name, contents=[prompt], config=gen_config
            ),
        )

        if response.parts:
            return response.text.strip()
        return None

    @_api_key_handler
    async def generate_simple_response(
        self,
        prompt: str,
        generation_config: Dict,
        model_name: Optional[str] = None,
        client: Any = None,
    ) -> Optional[str]:
        """
        一个用于单次、非对话式文本生成的方法，允许传入完整的生成配置和可选的模型名称。
        非常适合用于如“礼物回应”、“投喂”等需要自定义生成参数的一次性任务。

        Args:
            prompt: 提供给模型的完整输入提示。
            generation_config: 一个包含生成参数的字典 (e.g., temperature, max_output_tokens).
            model_name: (可选) 指定要使用的模型。如果为 None，则使用默认的聊天模型。

        Returns:
            生成的文本字符串，如果失败则返回 None。
        """
        if not client:
            raise ValueError("装饰器未能提供客户端实例。")

        loop = asyncio.get_event_loop()
        gen_config = types.GenerateContentConfig(
            **generation_config, safety_settings=self.safety_settings
        )
        final_model_name = model_name or self.model_name

        response = await loop.run_in_executor(
            self.executor,
            lambda: client.models.generate_content(
                model=final_model_name, contents=[prompt], config=gen_config
            ),
        )

        if response.parts:
            return response.text.strip()

        log.warning(f"generate_simple_response 未能生成有效内容。API 响应: {response}")
        if response.prompt_feedback and response.prompt_feedback.block_reason:
            log.warning(
                f"请求可能被安全策略阻止，原因: {response.prompt_feedback.block_reason}"
            )

        return None

    @_api_key_handler
    async def generate_thread_praise(
        self, conversation_history: List[Dict[str, Any]], client: Any = None
    ) -> Optional[str]:
        """
        专用于生成帖子夸奖的方法。
        现在接收一个由 prompt_service 构建好的完整对话历史。

        Args:
            conversation_history: 完整的对话历史列表。
            client: (由装饰器注入) Gemini 客户端。

        Returns:
            生成的夸奖文本，如果失败则返回 None。
        """
        if not client:
            raise ValueError("装饰器未能提供客户端实例。")

        loop = asyncio.get_event_loop()
        gen_config = types.GenerateContentConfig(
            **app_config.GEMINI_THREAD_PRAISE_CONFIG,
            safety_settings=self.safety_settings,
        )
        final_model_name = self.model_name

        final_contents = self._prepare_api_contents(conversation_history)

        # 如果开启了 AI 完整上下文日志，则打印到终端
        if app_config.DEBUG_CONFIG["LOG_AI_FULL_CONTEXT"]:
            log.info("--- 暖贴功能 · 完整 AI 上下文 ---")
            log.info(
                json.dumps(
                    [
                        self._serialize_parts_for_logging_full(content)
                        for content in final_contents
                    ],
                    ensure_ascii=False,
                    indent=2,
                )
            )
            log.info("------------------------------------")

        response = await loop.run_in_executor(
            self.executor,
            lambda: client.models.generate_content(
                model=final_model_name, contents=final_contents, config=gen_config
            ),
        )

        if response.parts:
            return response.text.strip()

        log.warning(f"generate_thread_praise 未能生成有效内容。API 响应: {response}")
        if response.prompt_feedback and response.prompt_feedback.block_reason:
            log.warning(
                f"请求可能被安全策略阻止，原因: {response.prompt_feedback.block_reason}"
            )

        return None

    async def summarize_for_rag(
        self,
        latest_query: str,
        user_name: str,
        conversation_history: Optional[List[Dict[str, any]]] = None,
    ) -> str:
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

        prompt = prompt_service.build_rag_summary_prompt(
            latest_query, user_name, conversation_history
        )
        summarized_query = await self.generate_text(
            prompt, temperature=0.0, model_name=app_config.QUERY_REWRITING_MODEL
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

    @_api_key_handler
    async def generate_text_with_image(
        self, prompt: str, image_bytes: bytes, mime_type: str, client: Any = None
    ) -> Optional[str]:
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
        if not client:
            raise ValueError("装饰器未能提供客户端实例。")

        # --- 新增：处理 GIF 图片 ---
        if mime_type == "image/gif":
            try:
                log.info("检测到 GIF 图片，尝试提取第一帧...")
                with Image.open(io.BytesIO(image_bytes)) as img:
                    # 寻求第一帧并转换为 RGBA 以确保兼容性
                    img.seek(0)
                    # 创建一个新的 BytesIO 对象来保存转换后的图片
                    output_buffer = io.BytesIO()
                    # 将图片保存为 PNG 格式
                    img.save(output_buffer, format="PNG")
                    # 获取转换后的字节数据
                    image_bytes = output_buffer.getvalue()
                    # 更新 MIME 类型
                    mime_type = "image/png"
                    log.info("成功将 GIF 第一帧转换为 PNG。")
            except Exception as e:
                log.error(f"处理 GIF 图片时出错: {e}", exc_info=True)
                return "呜哇，我的眼睛跟不上啦！有点看花眼了"
        # --- GIF 处理结束 ---

        request_contents = [
            prompt,
            types.Part(inline_data=types.Blob(mime_type=mime_type, data=image_bytes)),
        ]
        gen_config = types.GenerateContentConfig(
            **app_config.GEMINI_VISION_GEN_CONFIG, safety_settings=self.safety_settings
        )

        response = await client.aio.models.generate_content(
            model=self.model_name, contents=request_contents, config=gen_config
        )

        if response.parts:
            return response.text.strip()
        elif response.prompt_feedback and response.prompt_feedback.block_reason:
            log.warning(
                f"图文生成请求被安全策略阻止: {response.prompt_feedback.block_reason}"
            )
            return "为啥要投喂色图啊喂"

        log.warning(f"未能为图文生成有效回复。Response: {response}")
        return "我好像没看懂这张图里是什么，可以换一张或者稍后再试试吗？"

    @_api_key_handler
    async def generate_confession_response(
        self, prompt: str, client: Any = None
    ) -> Optional[str]:
        """
        专用于生成忏悔回应的方法。
        """
        if not client:
            raise ValueError("装饰器未能提供客户端实例。")

        gen_config = types.GenerateContentConfig(
            **app_config.GEMINI_CONFESSION_GEN_CONFIG,
            safety_settings=self.safety_settings,
        )
        final_model_name = self.model_name

        if app_config.DEBUG_CONFIG["LOG_AI_FULL_CONTEXT"]:
            log.info("--- 忏悔功能 · 完整 AI 上下文 ---")
            log.info(prompt)
            log.info("------------------------------------")

        response = await client.aio.models.generate_content(
            model=final_model_name, contents=[prompt], config=gen_config
        )

        if response.parts:
            return response.text.strip()

        log.warning(
            f"generate_confession_response 未能生成有效内容。API 响应: {response}"
        )
        if response.prompt_feedback and response.prompt_feedback.block_reason:
            log.warning(
                f"请求可能被安全策略阻止，原因: {response.prompt_feedback.block_reason}"
            )

        return None


# 全局实例
gemini_service = GeminiService()

# --- OpenAI 支持 ---
# 导入 OpenAI 服务和路由器
try:
    from src.chat.services.openai_service import openai_service
    from src.chat.services.ai_service_router import AIServiceRouter

    # 创建路由器实例，替代原有的 gemini_service
    ai_service = AIServiceRouter(gemini_service, openai_service)
    log.info("AI 服务路由器初始化成功")
except Exception as e:
    log.warning(f"无法初始化 OpenAI 服务，将仅使用 Gemini: {e}")
    # 如果 OpenAI 初始化失败，ai_service 指向 gemini_service
    ai_service = gemini_service
