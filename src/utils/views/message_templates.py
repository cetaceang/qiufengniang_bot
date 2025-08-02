# -*- coding: utf-8 -*-

import discord
from discord.ui import View, Button, button
import logging
from typing import Dict
from typing import Optional

from ...utils.database import db_manager
from .ui_elements import BackButton
from ... import config

log = logging.getLogger(__name__)

class MessageTemplatesView(View):
    """消息模板配置的主视图"""

    def __init__(self, main_interaction: discord.Interaction):
        super().__init__(timeout=180)
        self.main_interaction = main_interaction
        self.guild_id = main_interaction.guild.id
        
        self.add_item(BackButton())
        self.populate_buttons()

    def populate_buttons(self):
        """动态添加模板编辑按钮"""
        for item in self.children[:]:
            if isinstance(item, TemplateEditButton):
                self.remove_item(item)

        self.templates = db_manager.get_all_message_templates(self.guild_id)
        row = 1
        for name, details in config.TEMPLATE_TYPES.items():
            is_set = self.templates.get(name) is not None
            style = discord.ButtonStyle.success if is_set else discord.ButtonStyle.secondary
            self.add_item(TemplateEditButton(
                template_name=name,
                label=details["label"],
                style=style,
                emoji=details["emoji"],
                row=row
            ))
            row += 1

    @staticmethod
    def get_embed(guild: discord.Guild, templates: dict) -> discord.Embed:
        """生成消息模板配置的 Embed"""
        embed = discord.Embed(
            title="📝 消息模板配置",
            description="在这里，您可以自定义机器人在引导流程中发送给用户的各类消息。\n点击下方按钮以编辑对应的消息模板。",
            color=config.EMBED_COLOR_INFO
        )
        
        templates_to_show = {
            "welcome_message": config.TEMPLATE_TYPES["welcome_message"],
            "final_message": config.TEMPLATE_TYPES["final_message"]
        }
        for name, details in templates_to_show.items():
            status = "✅ 已设置" if templates.get(name) else "❌ 未设置"
            embed.add_field(name=f"{details['emoji']} {details['label']}", value=f"状态: {status}\n{details['description']}", inline=False)
            
        return embed

    async def refresh(self, interaction: Optional[discord.Interaction] = None):
        """
        刷新视图以显示最新状态。
        """
        self.populate_buttons()
        embed = self.get_embed(self.main_interaction.guild, self.templates)
        await self.main_interaction.edit_original_response(embed=embed, view=self)


class TemplateEditButton(Button):
    """编辑模板的按钮"""
    def __init__(self, template_name: str, label: str, style: discord.ButtonStyle, emoji: str, row: int):
        super().__init__(label=label, style=style, emoji=emoji, row=row)
        self.template_name = template_name

    async def callback(self, interaction: discord.Interaction):
        """打开模板编辑模态框"""
        # 延迟导入以避免循环依赖
        from ..modals.template_modal import TemplateModal
        
        current_template = db_manager.get_message_template(interaction.guild_id, self.template_name)
        modal = TemplateModal(
            template_name=self.template_name,
            current_data=current_template,
            parent_view=self.view
        )
        try:
            await interaction.response.send_modal(modal)
        except discord.NotFound:
            # 这通常发生在原始交互已超时的情况下
            try:
                await interaction.followup.send(
                    "❌ 操作超时，此次交互已失效。请重新打开管理面板再试一次。",
                    ephemeral=True
                )
            except discord.HTTPException:
                pass # 如果连 followup 都失败，就只能放弃了