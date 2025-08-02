# -*- coding: utf-8 -*-

import discord
from discord.ui import View, Select, Button, button
import logging
from typing import List

from ...utils.database import db_manager
from .ui_elements import BackButton
from ... import config

log = logging.getLogger(__name__)

class RoleConfigurationView(View):
    """身份组配置界面的视图"""

    def __init__(self, main_interaction: discord.Interaction):
        super().__init__(timeout=180)
        self.main_interaction = main_interaction
        self.guild_id = main_interaction.guild.id
        self.trigger_roles = []
        self.selected_role_ids = None

        self.add_item(BackButton())
        self.populate_items()

    @staticmethod
    def get_embed(guild: discord.Guild, trigger_roles: List[dict]) -> discord.Embed:
        """生成身份组配置的 Embed"""
        embed = discord.Embed(
            title="🛂 身份组配置",
            description="请在下方的多选菜单中，选择一个或多个身份组。\n当新用户获得**任何一个**您选择的身份组时，机器人将自动向其发起引导流程。",
            color=config.EMBED_COLOR_INFO
        )
        
        current_roles_ids = [row['role_id'] for row in trigger_roles]
        if not current_roles_ids:
            role_info = "目前没有设置任何触发身份组。"
        else:
            role_mentions = []
            for role_id in current_roles_ids:
                role = guild.get_role(role_id)
                role_mentions.append(role.mention if role else f"`未知身份组 (ID: {role_id})`")
            role_info = " ".join(role_mentions)
            
        embed.add_field(name="当前触发身份组", value=role_info, inline=False)
        return embed

    def populate_items(self):
        """加载或刷新动态组件"""
        for item in self.children[:]:
            if isinstance(item, (RoleSelect, SaveButton)):
                self.remove_item(item)
        
        self.trigger_roles = db_manager.get_trigger_roles(self.guild_id)
        self.add_item(RoleSelect(self))
        self.add_item(SaveButton())

    async def refresh(self):
        """刷新视图"""
        self.populate_items()
        embed = self.get_embed(self.main_interaction.guild, self.trigger_roles)
        await self.main_interaction.edit_original_response(embed=embed, view=self)

# --- UI 组件 ---

class RoleSelect(Select):
    """选择身份组的多选下拉菜单"""
    def __init__(self, parent_view: View):
        self.parent_view = parent_view
        guild = parent_view.main_interaction.guild
        
        current_roles_ids = {str(row['role_id']) for row in parent_view.trigger_roles}
        
        options = []
        sorted_roles = sorted(guild.roles, key=lambda r: r.position, reverse=True)
        for role in sorted_roles:
            if role.is_default():
                continue
            
            is_default = str(role.id) in current_roles_ids
            
            options.append(
                discord.SelectOption(
                    label=role.name,
                    value=str(role.id),
                    emoji="👑",
                    default=is_default
                )
            )
        
        if len(options) > 25:
            options = options[:25]
            placeholder = "选择触发身份组 (仅显示前25个)..."
        else:
            placeholder = "选择一个或多个触发身份组..."

        super().__init__(
            placeholder=placeholder,
            options=options,
            min_values=0,
            max_values=len(options),
            row=1
        )

    async def callback(self, interaction: discord.Interaction):
        # 将选择的 role_ids 存储在视图中，等待保存
        self.view.selected_role_ids = [int(v) for v in self.values]
        await interaction.response.defer() # 仅确认交互，不做任何事

class SaveButton(Button):
    """保存身份组设置的按钮"""
    def __init__(self):
        super().__init__(label="保存设置", style=discord.ButtonStyle.success, emoji="💾", row=2)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        # 从视图中获取已选择的 role_ids
        # 如果用户没有操作过下拉菜单，selected_role_ids 可能不存在
        selected_ids = getattr(self.view, 'selected_role_ids', None)

        if selected_ids is None:
            # 如果用户未动过下拉菜单，则无需保存
            await interaction.followup.send("ℹ️ 配置未发生变化，无需保存。", ephemeral=True)
            return

        try:
            db_manager.set_trigger_roles(interaction.guild_id, selected_ids)
            await interaction.followup.send("✅ 触发身份组配置已成功保存！", ephemeral=True)
            # 刷新主视图以显示更新后的状态
            await self.view.refresh()
        except Exception as e:
            log.error(f"保存在服务器 {interaction.guild_id} 的身份组配置时出错: {e}", exc_info=True)
            await interaction.followup.send("❌ 保存失败，发生了一个内部错误。", ephemeral=True)