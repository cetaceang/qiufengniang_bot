# -*- coding: utf-8 -*-

import logging
import discord
from typing import Optional
import asyncio

from ..services.gemini_service import gemini_service
from config.thread_prompts import THREAD_ANALYSIS_PROMPT

log = logging.getLogger(__name__)

class ThreadAnalyzerService:
    """
    负责分析Discord帖子内容的服务。
    """
    def __init__(self):
        pass

    async def analyze_thread_content(self, thread_content: str) -> str:
        """
        使用AI模型分析帖子内容并生成简短评价。
        """
        if not gemini_service.is_available():
            return "抱歉，AI服务暂时不可用，无法评价帖子。"

        try:
            # 构建AI的输入消息
            ai_message = THREAD_ANALYSIS_PROMPT.format(thread_content=thread_content)
            
            # 调用Gemini服务生成回复
            # 注意：这里我们不使用用户ID和guild_id，因为这是对帖子内容的独立评价，不涉及用户上下文
            # 我们可以使用一个固定的ID，或者根据需求调整gemini_service.generate_response的签名
            # 为了简化，这里暂时使用0作为user_id和guild_id
            ai_response = await gemini_service.generate_response(
                user_id=0, # 帖子分析不关联特定用户上下文
                guild_id=0, # 帖子分析不关联特定服务器上下文
                message=ai_message
            )
            
            log.info(f"已为帖子内容生成AI评价: {ai_response}")
            return ai_response

        except Exception as e:
            log.error(f"分析帖子内容时出错: {e}")
            # 提供一个符合类脑娘人设的回退消息
            return "哎呀，这个帖子有点深奥，类脑娘暂时还不太明白呢！不过，谢谢你愿意分享哦！✨"

# 全局实例
thread_analyzer_service = ThreadAnalyzerService()