# -*- coding: utf-8 -*-

import discord
from discord.ext import commands
from discord import app_commands
import logging
from datetime import datetime, timedelta
from src.chat.utils.database import chat_db_manager
from src.config import DEVELOPER_USER_IDS

log = logging.getLogger(__name__)

def is_developer():
    """检查用户是否是开发者"""
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.user.id not in DEVELOPER_USER_IDS:
            await interaction.response.send_message("你没有权限使用此命令。", ephemeral=True)
            return False
        return True
    return app_commands.check(predicate)

class BlacklistAdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="封禁", description="将用户加入黑名单 (仅开发者可用)")
    @app_commands.describe(user_id="要封禁的用户ID", duration_minutes="封禁时长(分钟)")
    @app_commands.default_permissions(manage_guild=True)
    @is_developer()
    async def blacklist_user(self, interaction: discord.Interaction, user_id: str, duration_minutes: int):
        guild_id = interaction.guild.id if interaction.guild else 0
        
        try:
            target_user_id = int(user_id)
        except ValueError:
            await interaction.response.send_message("请输入有效的用户ID。", ephemeral=True)
            return

        try:
            if await chat_db_manager.is_user_blacklisted(target_user_id, guild_id):
                await interaction.response.send_message(f"用户 <@{target_user_id}> 已经在黑名单中。", ephemeral=True)
                return

            expires_at = datetime.utcnow() + timedelta(minutes=duration_minutes)
            await chat_db_manager.add_to_blacklist(target_user_id, guild_id, expires_at)
            
            await interaction.response.send_message(f"已将用户 <@{target_user_id}> 加入黑名单，时长 {duration_minutes} 分钟。", ephemeral=True)
            log.info(f"开发者 {interaction.user} 将用户 {target_user_id} 加入黑名单，时长 {duration_minutes} 分钟。")
        except Exception as e:
            log.error(f"封禁用户时出错: {e}", exc_info=True)
            await interaction.response.send_message("封禁用户时发生错误，请检查日志。", ephemeral=True)

    @app_commands.command(name="解封", description="将用户从黑名单中移除 (仅开发者可用)")
    @app_commands.describe(user_id="要解封的用户ID")
    @app_commands.default_permissions(manage_guild=True)
    @is_developer()
    async def unblacklist_user(self, interaction: discord.Interaction, user_id: str):
        guild_id = interaction.guild.id if interaction.guild else 0
        try:
            target_user_id = int(user_id)
        except ValueError:
            await interaction.response.send_message("请输入有效的用户ID。", ephemeral=True)
            return
            
        try:
            if not await chat_db_manager.is_user_blacklisted(target_user_id, guild_id):
                await interaction.response.send_message(f"用户 <@{target_user_id}> 不在黑名单中。", ephemeral=True)
                return

            await chat_db_manager.remove_from_blacklist(target_user_id, guild_id)
            await interaction.response.send_message(f"已将用户 <@{target_user_id}> 从黑名单中移除。", ephemeral=True)
            log.info(f"开发者 {interaction.user} 将用户 {target_user_id} 从黑名单中移除。")
        except Exception as e:
            log.error(f"解封用户时出错: {e}", exc_info=True)
            await interaction.response.send_message("解封用户时发生错误，请检查日志。", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(BlacklistAdminCog(bot))