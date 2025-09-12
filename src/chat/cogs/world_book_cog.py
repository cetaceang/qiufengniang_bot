# -*- coding: utf-8 -*-

import discord
from discord.ext import commands, tasks
import logging
import asyncio
import sys
import os

# 添加项目根目录到 sys.path，以便导入脚本
current_script_path = os.path.abspath(__file__)
script_dir = os.path.dirname(current_script_path)
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(script_dir))))
sys.path.insert(0, project_root)

from scripts.build_vector_index import main as build_vector_index_main
from src.chat.config.chat_config import WORLD_BOOK_CONFIG

log = logging.getLogger(__name__)

class WorldBookCog(commands.Cog):
    """处理世界之书相关功能的Cog，包括定时更新向量数据库"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # 启动定时任务
        self.update_vector_index.start()
    
    def cog_unload(self):
        """当Cog被卸载时，取消定时任务"""
        self.update_vector_index.cancel()
    
    @tasks.loop(hours=WORLD_BOOK_CONFIG["VECTOR_INDEX_UPDATE_INTERVAL_HOURS"])
    async def update_vector_index(self):
        """
        定时执行向量数据库更新任务。
        """
        try:
            interval_hours = WORLD_BOOK_CONFIG["VECTOR_INDEX_UPDATE_INTERVAL_HOURS"]
            log.info(f"开始执行定时向量数据库更新任务（每{interval_hours}小时执行一次）...")
            # 运行向量索引构建脚本
            await build_vector_index_main()
            log.info("定时向量数据库更新任务执行完成。")
        except Exception as e:
            log.error(f"执行定时向量数据库更新任务时出错: {e}", exc_info=True)
    
    @update_vector_index.before_loop
    async def before_update_vector_index(self):
        """
        在定时任务开始前等待机器人准备就绪。
        """
        log.info("等待机器人准备就绪以启动定时向量数据库更新任务...")
        await self.bot.wait_until_ready()
        interval_hours = WORLD_BOOK_CONFIG["VECTOR_INDEX_UPDATE_INTERVAL_HOURS"]
        log.info(f"机器人已准备就绪，定时向量数据库更新任务将在{interval_hours}小时后首次执行。")

async def setup(bot: commands.Bot):
    """将这个Cog添加到机器人中"""
    await bot.add_cog(WorldBookCog(bot))