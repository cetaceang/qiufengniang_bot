# -*- coding: utf-8 -*-

import discord
from discord.ext import commands
from discord import app_commands
import logging
from datetime import datetime, timedelta
import random

from src.chat.utils.database import chat_db_manager

log = logging.getLogger(__name__)

# 特定用户ID列表，只有这些用户可以使用/unblacklist命令
# TODO: 替换为实际的用户ID
AUTHORIZED_USER_IDS = [1378211909425299507,1355139188579762196,741904963608903754,1256873423167164436,1091264046482858106,1288762128068509726]

class BlacklistAdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="unblacklist", description="将用户从黑名单中移除 (特定用户专用)")
    @app_commands.describe(user="要解拉黑的用户")
    async def unblacklist_user(self, interaction: discord.Interaction, user: discord.User):
        # 检查交互的用户是否在授权列表中
        if interaction.user.id not in AUTHORIZED_USER_IDS:
            await interaction.response.send_message("你没有权限使用此命令。", ephemeral=True)
            return
            
        guild_id = interaction.guild.id if interaction.guild else 0
        try:
            if not await chat_db_manager.is_user_blacklisted(user.id, guild_id):
                await interaction.response.send_message(f"用户 {user.mention} 不在黑名单中。", ephemeral=True)
                return

            await chat_db_manager.remove_from_blacklist(user.id, guild_id)
            await interaction.response.send_message(f"已将用户 {user.mention} 从黑名单中移除。", ephemeral=True)
            log.info(f"授权用户 {interaction.user} 将用户 {user.id} 从黑名单中移除。")
        except Exception as e:
            log.error(f"解拉黑用户时出错: {e}", exc_info=True)
            await interaction.response.send_message("解拉黑用户时发生错误，请检查日志。", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(BlacklistAdminCog(bot))