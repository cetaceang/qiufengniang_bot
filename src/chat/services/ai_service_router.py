# -*- coding: utf-8 -*-

import os
import logging
from typing import Optional, Dict, List, Any

log = logging.getLogger(__name__)


class AIServiceRouter:
    """AI 服务路由器，根据配置选择使用 Gemini 或 OpenAI"""

    def __init__(self, gemini_service, openai_service):
        self.gemini_service = gemini_service
        self.openai_service = openai_service

        # 从环境变量读取配置
        self.use_openai = os.getenv("USE_OPENAI_FOR_CHAT", "false").lower() == "true"

        if self.use_openai:
            log.info("AI 服务路由器: 核心对话功能将使用 OpenAI")
        else:
            log.info("AI 服务路由器: 核心对话功能将使用 Gemini")

    def set_bot(self, bot):
        """注入 Discord Bot 实例到两个服务"""
        self.gemini_service.set_bot(bot)
        self.openai_service.set_bot(bot)

    async def generate_response(self, *args, **kwargs) -> str:
        """路由核心对话生成到选定的服务"""
        if self.use_openai:
            return await self.openai_service.generate_response(*args, **kwargs)
        else:
            return await self.gemini_service.generate_response(*args, **kwargs)

    # --- 以下方法始终使用 Gemini ---

    async def generate_embedding(
        self,
        text: str,
        task_type: str = "retrieval_document",
        title: Optional[str] = None,
    ) -> Optional[List[float]]:
        """嵌入向量生成始终使用 Gemini"""
        return await self.gemini_service.generate_embedding(text, task_type, title)

    async def generate_text(
        self,
        prompt: str,
        temperature: float = None,
        model_name: Optional[str] = None,
    ) -> Optional[str]:
        """简单文本生成（用于查询重写等）"""
        if self.use_openai:
            return await self.openai_service.generate_text(prompt, temperature, model_name)
        else:
            return await self.gemini_service.generate_text(prompt, temperature, model_name)

    async def generate_simple_response(
        self,
        prompt: str,
        generation_config: Dict,
        model_name: Optional[str] = None,
    ) -> Optional[str]:
        """简单回复生成始终使用 Gemini"""
        return await self.gemini_service.generate_simple_response(
            prompt, generation_config, model_name
        )

    async def generate_thread_praise(
        self, conversation_history: List[Dict[str, Any]]
    ) -> Optional[str]:
        """帖子夸奖生成始终使用 Gemini"""
        return await self.gemini_service.generate_thread_praise(conversation_history)

    async def summarize_for_rag(
        self,
        latest_query: str,
        user_name: str,
        conversation_history: Optional[List[Dict[str, any]]] = None,
    ) -> str:
        """RAG 查询总结始终使用 Gemini"""
        return await self.gemini_service.summarize_for_rag(
            latest_query, user_name, conversation_history
        )

    async def clear_user_context(self, user_id: int, guild_id: int):
        """清除用户上下文"""
        await self.gemini_service.clear_user_context(user_id, guild_id)

    def is_available(self) -> bool:
        """检查AI服务是否可用"""
        if self.use_openai:
            return self.openai_service.is_available()
        else:
            return self.gemini_service.is_available()

    async def generate_text_with_image(
        self, prompt: str, image_bytes: bytes, mime_type: str
    ) -> Optional[str]:
        """图文生成始终使用 Gemini"""
        return await self.gemini_service.generate_text_with_image(
            prompt, image_bytes, mime_type
        )

    async def generate_confession_response(self, prompt: str) -> Optional[str]:
        """忏悔回应生成始终使用 Gemini"""
        return await self.gemini_service.generate_confession_response(prompt)

    async def get_user_conversation_history(
        self, user_id: int, guild_id: int
    ) -> List[Dict]:
        """获取用户对话历史"""
        return await self.gemini_service.get_user_conversation_history(user_id, guild_id)
