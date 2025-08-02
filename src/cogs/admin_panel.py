# -*- coding: utf-8 -*-

import discord
from discord import app_commands
from discord.ext import commands
import logging

# 从我们自己的模块中导入
from ..utils.views.main_panel import MainPanelView
from .. import config

log = logging.getLogger(__name__)

def is_authorized(interaction: discord.Interaction) -> bool:
    """检查用户是否有权使用管理命令"""
    # 检查是否为开发者
    if interaction.user.id in config.DEVELOPER_USER_IDS:
        return True
    
    # 检查是否拥有管理员角色
    if isinstance(interaction.user, discord.Member):
        user_role_ids = {role.id for role in interaction.user.roles}
        if not user_role_ids.isdisjoint(config.ADMIN_ROLE_IDS):
            return True
            
    return False

class AdminPanel(commands.Cog):
    """
    包含所有与统一管理面板相关的命令。
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="新人引导管理面板", description="打开集成的多功能新人引导管理面板。")
    async def open_admin_panel(self, interaction: discord.Interaction):
        """
        显示主管理面板。
        """
        await interaction.response.defer(ephemeral=True)

        if not interaction.guild:
            await interaction.followup.send("此命令只能在服务器中使用。", ephemeral=True)
            return

        if not is_authorized(interaction):
            await interaction.followup.send("❌ 你没有权限使用此命令。", ephemeral=True)
            return
        
        embed = MainPanelView.get_main_embed(interaction.guild)
        view = MainPanelView(interaction)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)


async def setup(bot: commands.Bot):
    """将这个 Cog 添加到机器人中"""
    await bot.add_cog(AdminPanel(bot))