# -*- coding: utf-8 -*-

import discord
from discord.ext import commands
import logging
import asyncio

from ..services.thread_analyzer_service import thread_analyzer_service

log = logging.getLogger(__name__)

class ThreadAnalyzerCog(commands.Cog):
    """
    监听新帖子创建，并在延迟后对首楼内容进行AI评价。
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread):
        """
        监听新帖子的创建事件。
        """
        log.info(f"检测到新帖子创建: '{thread.name}' (ID: {thread.id})")

        # 延迟5分钟后进行分析
        await asyncio.sleep(300) # 300秒 = 5分钟

        try:
            # 获取首楼消息
            # thread.starter_message 会在帖子创建时立即可用
            # 但为了确保内容完整性，我们也可以fetch_message
            starter_message = await thread.fetch_message(thread.id) # 帖子的ID就是首楼消息的ID

            if not starter_message or not starter_message.content:
                log.warning(f"无法获取帖子 '{thread.name}' (ID: {thread.id}) 的首楼内容。")
                return

            thread_content = starter_message.content
            log.info(f"正在分析帖子 '{thread.name}' 的首楼内容: {thread_content[:100]}...") # 记录前100字

            # 调用服务进行AI分析
            ai_evaluation = await thread_analyzer_service.analyze_thread_content(thread_content)

            # 将AI评价发送到帖子中
            await thread.send(f"类脑娘对这个帖子的评价是：\n{ai_evaluation}")
            log.info(f"已在帖子 '{thread.name}' 中发布AI评价。")

        except Exception as e:
            log.error(f"处理新帖子 '{thread.name}' (ID: {thread.id}) 时出错: {e}")
            # 可以在这里选择是否发送错误消息到帖子中
            # await thread.send("抱歉，类脑娘在评价这个帖子时遇到了问题。")

async def setup(bot: commands.Bot):
    """将这个Cog添加到机器人中"""
    await bot.add_cog(ThreadAnalyzerCog(bot))