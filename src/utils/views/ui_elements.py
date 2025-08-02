# -*- coding: utf-8 -*-

import discord
from discord.ui import Button

class BackButton(Button):
    """一个通用的返回主菜单按钮"""
    def __init__(self, row: int = 0):
        super().__init__(label="返回主菜单", style=discord.ButtonStyle.grey, emoji="↩️", row=row)

    async def callback(self, interaction: discord.Interaction):
        # 延迟导入以避免循环依赖
        from src.utils.views.main_panel import MainPanelView
        
        # 确保 self.view.main_interaction 存在
        if not hasattr(self.view, 'main_interaction'):
            await interaction.response.send_message("发生错误，无法返回主菜单。", ephemeral=True)
            return

        await interaction.response.defer()
        embed = MainPanelView.get_main_embed(interaction.guild)
        view = MainPanelView(self.view.main_interaction)
        await self.view.main_interaction.edit_original_response(embed=embed, view=view)