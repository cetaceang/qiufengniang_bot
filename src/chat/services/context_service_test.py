# -*- coding: utf-8 -*-

import logging
from typing import Optional, Dict, List
import discord
import re
from src import config
from src.chat.config import chat_config
from src.chat.utils.database import chat_db_manager
from src.chat.services.regex_service import regex_service
from src.chat.features.affection.service.affection_service import affection_service
from src.chat.features.world_book.services.world_book_service import world_book_service

log = logging.getLogger(__name__)

class ContextServiceTest:
    """上下文管理服务测试版本，用于对比新的上下文处理逻辑"""
    
    def __init__(self):
        self.bot = None
    
    def set_bot_instance(self, bot: 'discord.ext.commands.Bot'):
        self.bot = bot
        log.info("ContextServiceTest 已设置 bot 实例。")
    
    async def get_formatted_channel_history_new(self, channel_id: int, user_id: int, guild_id: int, limit: int = chat_config.CHANNEL_MEMORY_CONFIG["formatted_history_limit"], exclude_message_id: Optional[int] = None) -> List[Dict[str, any]]:
        """
        获取结构化的频道对话历史。
        此方法将历史消息与用户的最新消息分离，以引导模型只回复最新内容。
        """
        if not self.bot:
            log.error("ContextServiceTest 的 bot 实例未设置，无法获取频道消息历史。")
            return []

        channel = self.bot.get_channel(channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            log.warning(f"未找到或无效的文本频道 ID: {channel_id}")
            return []

        history_parts = []
        latest_user_message_content = ""
        
        try:
            guild_id = channel.guild.id if channel.guild else 0
            anchor_message_id = await chat_db_manager.get_channel_memory_anchor(guild_id, channel_id)
            
            after_message = None
            # 获取比限制多一条，以便找到最新的那条用户消息
            fetch_limit = limit + 1 
            if anchor_message_id:
                try:
                    after_message = discord.Object(id=anchor_message_id)
                    fetch_limit = limit + 2
                    log.info(f"找到频道 {channel_id} 的记忆锚点: {anchor_message_id}，将从此消息之后开始获取历史。")
                except Exception as e:
                    log.error(f"创建 discord.Object 失败，锚点ID {anchor_message_id} 可能无效: {e}")

            history_messages = [msg async for msg in channel.history(limit=fetch_limit, after=after_message)]

            if not after_message:
                history_messages.reverse()

            # 寻找并分离出最新的用户消息
            latest_user_message_index = -1
            for i in range(len(history_messages) - 1, -1, -1):
                msg = history_messages[i]
                is_bot = msg.author.id == self.bot.user.id or \
                         (config.BRAIN_GIRL_APP_ID and msg.author.id == config.BRAIN_GIRL_APP_ID)
                if not is_bot and msg.id == exclude_message_id:
                    latest_user_message_index = i
                    break
            
            if latest_user_message_index != -1:
                latest_user_message = history_messages.pop(latest_user_message_index)
                latest_user_message_content = self.clean_message_content(latest_user_message.content, latest_user_message.guild)

            # 处理剩余的历史消息
            for msg in history_messages:
                is_irrelevant_type = msg.type not in (discord.MessageType.default, discord.MessageType.reply)
                if is_irrelevant_type or msg.id == exclude_message_id:
                    continue

                clean_content = self.clean_message_content(msg.content, msg.guild)
                if not clean_content and not msg.attachments:
                    continue

                reply_info = ""
                if msg.reference and msg.reference.message_id:
                    try:
                        ref_msg = await channel.fetch_message(msg.reference.message_id)
                        if ref_msg and ref_msg.author:
                            reply_info = f'[回复 {ref_msg.author.display_name}] '
                    except (discord.NotFound, discord.Forbidden):
                        pass
                
                history_parts.append(f'{reply_info}{msg.author.display_name}: {clean_content}')

            # 构建最终的上下文列表
            final_context = []
            
            # 1. 将所有历史记录打包成一个 user 消息作为背景
            if history_parts:
                background_prompt = "以上是历史对话和相关背景信息，请你只针对用户的最新消息进行回复：\n\n" + "\n\n".join(history_parts)
                final_context.append({
                    "role": "user",
                    "parts": [background_prompt]
                })

            # 2. 注入好感度和用户档案作为 model 的确认和上下文提示
            affection_status = await affection_service.get_affection_status(user_id, guild_id)
            affection_level_prompt = affection_status.get("prompt", "")
            
            user_profile_prompt = ""
            user_profile = world_book_service.get_profile_by_discord_id(str(user_id))
            if user_profile:
                profile_content = user_profile.get('content', {})
                if isinstance(profile_content, dict):
                    profile_details = [f"{key}: {value}" for key, value in profile_content.items() if value and value != '未提供']
                    if profile_details:
                        user_profile_prompt = "\n\n这是与你对话的用户的已知信息：\n" + "\n".join(profile_details)
            
            model_reply = f"好的,我已了解以上背景信息,会针对用户的最新消息进行回复。{affection_level_prompt}{user_profile_prompt}"
            final_context.append({
                "role": "model",
                "parts": [model_reply]
            })
            
            # 3. 将用户的最新消息作为最后一个 user 消息
            if latest_user_message_content:
                final_context.append({
                    "role": "user",
                    "parts": [latest_user_message_content]
                })

            return final_context
        except discord.Forbidden:
            log.error(f"机器人没有权限读取频道 {channel_id} 的消息历史。")
            return []
        except Exception as e:
            log.error(f"获取并格式化频道 {channel_id} 消息历史时出错: {e}")
            return []
    
    def clean_message_content(self, content: str, guild: Optional[discord.Guild]) -> str:
        """
        净化消息内容，移除或替换不适合模型处理的元素。
        """
        content = re.sub(r'https?://cdn\.discordapp\.com\S+', '', content)
        if guild:
            def replace_mention(match):
                user_id = int(match.group(1))
                member = guild.get_member(user_id)
                return f"@{member.display_name}" if member else "@未知用户"
            content = re.sub(r'<@!?(\d+)>', replace_mention, content)
        content = re.sub(r'<a?:\w+:\d+>', '', content)
        content = regex_service.clean_user_input(content)
        return content.strip()

# 全局实例
context_service_test = ContextServiceTest()