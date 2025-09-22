 # -*- coding: utf-8 -*-

import logging
import discord
from typing import Optional
import sqlite3
import json
import os

from src import config
from src.chat.services.gemini_service import gemini_service
from src.chat.config.thread_prompts import THREAD_PRAISE_PROMPT
from src.chat.config.prompts import SYSTEM_PROMPT
from src.chat.utils.prompt_utils import replace_emojis
from src.chat.utils.database import chat_db_manager

log = logging.getLogger(__name__)

class ThreadCommentorService:
    """处理新帖子评价功能的服务"""

    def __init__(self):
        self.world_book_db_path = os.path.join(config.DATA_DIR, 'world_book.sqlite3')

    async def _get_user_memory(self, user_id: int) -> str:
        """
        从世界书和主数据库中获取用户的个人记忆。
        """
        memory_parts = []

        # 1. 从世界书数据库获取用户档案
        try:
            with sqlite3.connect(self.world_book_db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT content_json FROM community_members WHERE discord_number_id = ?",
                    (str(user_id),)
                )
                row = cursor.fetchone()
                if row and row['content_json']:
                    profile = json.loads(row['content_json'])
                    profile_text = (
                        f"用户的公开档案：\n"
                        f"- 昵称: {profile.get('name', '未知')}\n"
                        f"- 性格: {profile.get('personality', '未知')}\n"
                        f"- 背景: {profile.get('background', '未知')}\n"

                        f"- 偏好: {profile.get('preferences', '未知')}"
                    )
                    memory_parts.append(profile_text)
        except Exception as e:
            log.error(f"从世界书数据库为用户 {user_id} 获取档案时出错: {e}")

        # 2. 从主数据库获取对话摘要
        try:
            user_profile = await chat_db_manager.get_user_profile(user_id)
            if user_profile and user_profile['personal_summary']:
                summary_text = f"我与该用户的过往对话摘要：\n{user_profile['personal_summary']}"
                memory_parts.append(summary_text)
        except Exception as e:
            log.error(f"从主数据库为用户 {user_id} 获取摘要时出错: {e}")

        if not memory_parts:
            return "关于这位用户，我暂时还没有任何记忆。"
        
        return "\n\n---\n\n".join(memory_parts)

    async def praise_new_thread(self, thread: discord.Thread, user_id: int, user_nickname: str) -> Optional[str]:
        """
        针对新创建的帖子生成一段结合用户记忆的个性化夸奖。
        """
        try:
            # 1. 获取帖子的初始消息
            if thread.starter_message:
                first_message = thread.starter_message
            else:
                first_message = await thread.fetch_message(thread.id)

            if not first_message or not first_message.content:
                log.info(f"帖子 '{thread.name}' (ID: {thread.id}) 没有有效的初始消息内容，跳过评价。")
                return None

            # 2. 准备帖子内容
            title = thread.name
            tags = ", ".join([tag.name for tag in thread.applied_tags])
            content = first_message.content
            max_content_length = 1500
            if len(content) > max_content_length:
                content = content[:max_content_length] + "..."
            thread_full_content = f"标题: {title}\n标签: {tags}\n内容: {content}"

            # 3. 获取用户记忆
            user_memory = await self._get_user_memory(user_id)

            # 4. 构建提示
            # 首先构建核心系统提示词
            from datetime import datetime, timezone, timedelta
            beijing_tz = timezone(timedelta(hours=8))
            current_beijing_time = datetime.now(beijing_tz).strftime('%Y年%m月%d日 %H:%M')
            core_prompt = SYSTEM_PROMPT.format(
                current_time=current_beijing_time,
                user_name=user_nickname
            )
            
            # 然后构建帖子夸奖提示词
            praise_prompt = THREAD_PRAISE_PROMPT.format(
                user_nickname=user_nickname,
                user_memory=user_memory,
                thread_content=thread_full_content
            )
            
            # 将两者结合
            prompt = f"{core_prompt}\n\n{praise_prompt}"
            
            log.info(f"为帖子 '{title}' 构建的最终Prompt:\n---\n{prompt}\n---")

            # 5. 调用 Gemini 服务生成夸奖
            praise_text = await gemini_service.generate_thread_praise(prompt)

            if praise_text:
                # 使用 prompt_utils 中的函数来处理表情符号
                processed_praise = replace_emojis(praise_text)
                log.info(f"成功为帖子 '{title}' 生成并处理后评价: {processed_praise}")
                return processed_praise
            else:
                log.warning(f"为帖子 '{title}' 生成评价时返回了空内容。")
                return None

        except discord.errors.NotFound:
            log.warning(f"无法找到帖子 {thread.id} 的初始消息，可能已被删除。")
            return None
        except Exception as e:
            log.error(f"为帖子 '{thread.name}' (ID: {thread.id}) 生成评价时发生意外错误: {e}", exc_info=True)
            return None

thread_commentor_service = ThreadCommentorService()