# -*- coding: utf-8 -*-

import discord
import logging
from typing import List, Dict, Any, Optional, Tuple
import re
import asyncio
import aiohttp

from src.chat.services.regex_service import regex_service
from src import config

log = logging.getLogger(__name__)

# 定义一个正则表达式来匹配自定义表情
# <a:emoji_name:emoji_id> (动态) 或 <:emoji_name:emoji_id> (静态)
EMOJI_REGEX = re.compile(r'<a?:(\w+):(\d+)>')

class MessageProcessor:
    """
    负责处理和解析 discord.Message 对象，提取用于 AI 对话所需的信息。
    """
    
    async def _fetch_image_aio(self, session: aiohttp.ClientSession, url: str, proxy: Optional[str] = None) -> Optional[bytes]:
        """下载图片"""
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5), proxy=proxy) as response:
                response.raise_for_status()
                return await response.read()
        except asyncio.TimeoutError:
            log.warning(f"下载表情图片超时: {url}")
            return None
        except aiohttp.ClientError as e:
            log.warning(f"下载表情图片失败: {url}, 错误: {e}")
            return None

    async def _extract_emojis_as_images(self, content: str) -> Tuple[str, List[Dict[str, Any]]]:
        """从文本中提取自定义表情，下载图片，并用占位符替换文本"""
        # log.debug(f"开始提取表情，接收到的内容: '{content}'")
        emoji_images = []
        tasks = []
        matches = list(EMOJI_REGEX.finditer(content))

        if not matches:
            return content, []

        proxy_url = config.PROXY_URL
        async with aiohttp.ClientSession() as session:
            # 准备所有下载任务
            for match in matches:
                emoji_name, emoji_id = match.groups()
                # 动态表情使用 .gif，静态使用 .png
                extension = 'gif' if match.group(0).startswith('<a:') else 'png'
                url = f"https://cdn.discordapp.com/emojis/{emoji_id}.{extension}"
                tasks.append(asyncio.create_task(self._fetch_image_aio(session, url, proxy=proxy_url)))

            # 并发执行下载
            results = await asyncio.gather(*tasks)

        # 处理下载结果并替换文本
        modified_content = content
        for match, image_bytes in zip(matches, results):
            if image_bytes:
                emoji_name = match.group(1)
                mime_type = 'image/gif' if match.group(0).startswith('<a:') else 'image/png'
                emoji_images.append({
                    'mime_type': mime_type,
                    'data': image_bytes,
                    'source': 'emoji',
                    'name': emoji_name
                })
                # 将原始表情文本替换为带名称的占位符，帮助模型理解
                modified_content = modified_content.replace(match.group(0), f"__EMOJI_{emoji_name}__", 1)
        
        return modified_content, emoji_images

    async def process_message(self, message: discord.Message) -> Dict[str, Any]:
        """
        处理传入的 discord 消息对象。

        Args:
            message (discord.Message): 用户发送的消息。

        Returns:
            Dict[str, Any]: 一个包含 'final_content' 和 'image_data_list' 的字典。
        """
        image_data_list = []

        # 1. 处理当前消息的图片附件
        if message.attachments:
            image_data_list.extend(await self._extract_images_from_attachments(message.attachments))

        # 2. 处理被回复的消息
        replied_message_content = ""
        if message.reference and message.reference.message_id:
            try:
                ref_msg = await message.channel.fetch_message(message.reference.message_id)
                if ref_msg and ref_msg.author:
                    # 清理被回复消息的文本
                    ref_content_cleaned = self._clean_message_content(ref_msg.content, ref_msg.mentions)
                    replied_message_content = f'[回复 @{ref_msg.author.display_name}: "{ref_content_cleaned}"] '
                    
                    # 提取被回复消息中的图片
                    if ref_msg.attachments:
                        image_data_list.extend(await self._extract_images_from_attachments(ref_msg.attachments))
            except (discord.NotFound, discord.Forbidden):
                log.warning(f"无法找到或无权访问被回复的消息 ID: {message.reference.message_id}")
            except Exception as e:
                log.error(f"处理被回复消息时出错: {e}")

        # 3. 从原始消息文本中提取表情
        content_with_placeholders, emoji_images = await self._extract_emojis_as_images(message.content)
        image_data_list.extend(emoji_images)

        # 4. 清理文本内容
        clean_content = self._clean_message_content(content_with_placeholders, message.mentions)

        # 5. 组合最终的文本内容
        final_content = f"{replied_message_content}{clean_content}"

        return {
            "final_content": final_content,
            "image_data_list": image_data_list
        }

    async def _extract_images_from_attachments(self, attachments: List[discord.Attachment]) -> List[Dict[str, Any]]:
        """从附件列表中提取图片数据。"""
        image_data_list = []
        for attachment in attachments:
            if attachment.content_type and attachment.content_type.startswith('image/'):
                try:
                    image_bytes = await attachment.read()
                    if image_bytes:
                        image_data_list.append({
                            'mime_type': attachment.content_type,
                            'data': image_bytes,
                            'source': 'attachment'
                        })
                        log.debug(f"成功读取图片附件: {attachment.filename}, 大小: {len(image_bytes)} 字节")
                except Exception as e:
                    log.error(f"读取图片附件 {attachment.filename} 时出错: {e}")
        return image_data_list

    def _clean_message_content(self, content: str, mentions: list) -> str:
        """
        清理消息内容，移除@mention部分，并清理括号内容。
        """
        # 移除所有@mention
        for user in mentions:
            content = content.replace(f'<@{user.id}>', '').replace(f'<@!{user.id}>', '')
        
        # 使用 regex_service 清理用户输入中的所有指定括号
        content = regex_service.clean_user_input(content)
        
        # 移除多余空格和换行
        content = content.strip()
        
        return content

# 创建一个单例
message_processor = MessageProcessor()