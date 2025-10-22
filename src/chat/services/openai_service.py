# -*- coding: utf-8 -*-

import os
import logging
from typing import Optional, Dict, List, Any
import asyncio
import json
import base64
import io

from openai import AsyncOpenAI
from openai import APIError, RateLimitError, APIConnectionError
from PIL import Image

from src.chat.config import chat_config as app_config
from src.chat.features.tools.tool_registry import tool_registry
from src.chat.features.tools.services.tool_service import ToolService

log = logging.getLogger(__name__)


class OpenAIService:
    """OpenAI AI 服务类，提供与 GeminiService 兼容的接口"""

    def __init__(self):
        self.bot = None  # 用于存储 Discord Bot 实例

        # 初始化 OpenAI 客户端
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            log.error("OPENAI_API_KEY 环境变量未设置！")
            raise ValueError("OPENAI_API_KEY is not set.")

        base_url = os.getenv("OPENAI_API_BASE_URL")
        if base_url:
            log.info(f"使用自定义 OpenAI API 端点: {base_url}")
            self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        else:
            log.info("使用默认 OpenAI API 端点。")
            self.client = AsyncOpenAI(api_key=api_key)

        self.model_name = app_config.OPENAI_MODEL

        # --- 工具配置 ---
        self.tool_service = ToolService()
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
        log.info("Discord Bot 实例已成功注入 OpenAIService。")

    def _convert_tools_to_openai_format(self) -> List[Dict]:
        """将工具定义转换为 OpenAI 格式"""
        if not self.tools:
            return []

        openai_tools = []
        for tool in self.tools:
            openai_tool = {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["parameters"]
                }
            }
            openai_tools.append(openai_tool)

        return openai_tools

    def _prepare_messages(self, conversation: List[Dict]) -> List[Dict]:
        """将对话历史转换为 OpenAI 消息格式"""
        messages = []
        for turn in conversation:
            role = turn.get("role")
            parts = turn.get("parts", [])

            if not (role and parts):
                continue

            # 转换角色名称
            if role == "model":
                role = "assistant"

            # 处理内容（支持文本和图片）
            content = []
            for part in parts:
                if isinstance(part, str):
                    content.append({"type": "text", "text": part})
                elif isinstance(part, Image.Image):
                    # 将 PIL.Image 转换为 base64
                    buffered = io.BytesIO()
                    part.save(buffered, format="PNG")
                    img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')

                    content.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{img_base64}"
                        }
                    })

            if content:
                # 如果只有一个文本部分，直接使用字符串；否则使用列表格式
                if len(content) == 1 and content[0].get("type") == "text":
                    messages.append({
                        "role": role,
                        "content": content[0]["text"]
                    })
                else:
                    # 包含图片或多个部分时，使用列表格式
                    messages.append({
                        "role": role,
                        "content": content
                    })

        return messages

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
    ) -> str:
        """生成AI回复（OpenAI实现）"""
        try:
            # 导入 prompt_service 来构建提示
            from src.chat.services.prompt_service import prompt_service

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

            # 2. 转换为 OpenAI 消息格式
            messages = self._prepare_messages(final_conversation)

            # 3. 准备工具调用
            openai_tools = self._convert_tools_to_openai_format()

            # 4. 调用 OpenAI API
            log.info(f"--- 正在为用户 {user_id} 调用 OpenAI API ---")

            kwargs = {
                "model": self.model_name,
                "messages": messages,
                "temperature": app_config.OPENAI_CHAT_CONFIG.get("temperature", 0.7),
                "max_tokens": app_config.OPENAI_CHAT_CONFIG.get("max_tokens", 2000),
            }

            if openai_tools:
                kwargs["tools"] = openai_tools
                kwargs["tool_choice"] = "auto"

            response = await self.client.chat.completions.create(**kwargs)

            log.info(f"--- 从 OpenAI 收到的原始响应 ---\n{response}")

            # 5. 处理工具调用
            message_obj = response.choices[0].message

            if message_obj.tool_calls:
                log.info(f"模型请求调用 {len(message_obj.tool_calls)} 个工具")

                # 将助手的消息添加到对话历史
                messages.append({
                    "role": "assistant",
                    "content": message_obj.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments
                            }
                        }
                        for tc in message_obj.tool_calls
                    ]
                })

                # 执行工具调用
                for tool_call in message_obj.tool_calls:
                    function_name = tool_call.function.name
                    function_args = json.loads(tool_call.function.arguments)

                    log.info(f"执行工具: {function_name}，参数: {function_args}")

                    # 这里需要适配工具执行逻辑
                    # 暂时返回一个占位符
                    tool_result = {"result": "工具调用功能开发中"}

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(tool_result, ensure_ascii=False)
                    })

                # 再次调用 API 获取最终回复
                response = await self.client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    temperature=app_config.OPENAI_CHAT_CONFIG.get("temperature", 0.7),
                    max_tokens=app_config.OPENAI_CHAT_CONFIG.get("max_tokens", 2000),
                )

                message_obj = response.choices[0].message

            # 6. 提取回复文本
            raw_response = message_obj.content or ""

            # 7. 更新对话历史
            from src.chat.services.context_service import context_service
            await context_service.update_user_conversation_history(
                user_id, guild_id, message if message else "", raw_response
            )

            # 8. 后处理（使用 gemini_service 的后处理逻辑）
            from src.chat.services.gemini_service import gemini_service
            formatted_response = await gemini_service._post_process_response(
                raw_response, user_id, guild_id
            )

            return formatted_response

        except RateLimitError as e:
            log.error(f"OpenAI API 速率限制: {e}")
            return "啊啊啊服务器要爆炸啦！现在有点忙不过来，你过一会儿再来找我玩吧！<生气>"
        except APIConnectionError as e:
            log.error(f"OpenAI API 连接错误: {e}")
            return "呜哇，有点晕嘞，等我休息一会儿 <伤心>"
        except APIError as e:
            log.error(f"OpenAI API 错误: {e}")
            return "抱歉，AI服务遇到了一个意料之外的错误，请稍后再试。"
        except Exception as e:
            log.error(f"生成回复时发生未知错误: {e}", exc_info=True)
            return "呜哇，有点晕嘞，等我休息一会儿 <伤心>"

    async def generate_text(
        self,
        prompt: str,
        temperature: float = None,
        model_name: Optional[str] = None,
    ) -> Optional[str]:
        """简单文本生成"""
        try:
            response = await self.client.chat.completions.create(
                model=model_name or self.model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature if temperature is not None else 0.7,
                max_tokens=1000,
            )

            return response.choices[0].message.content.strip()
        except Exception as e:
            log.error(f"生成文本时出错: {e}", exc_info=True)
            return None

    def is_available(self) -> bool:
        """检查AI服务是否可用"""
        return self.client is not None


# 全局实例
openai_service = OpenAIService()
