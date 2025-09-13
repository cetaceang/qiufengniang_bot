# -*- coding: utf-8 -*-

import discord
from discord.ext import commands
import logging

log = logging.getLogger(__name__)

class WorldBookCog(commands.Cog):
    """处理世界之书相关功能的Cog"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
async def setup(bot: commands.Bot):
    """将这个Cog添加到机器人中"""
    await bot.add_cog(WorldBookCog(bot))