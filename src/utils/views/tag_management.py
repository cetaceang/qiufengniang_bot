# -*- coding: utf-8 -*-

import discord
from discord.ui import View, Button, button
import logging

from ...utils.database import db_manager
from ...utils.modals.tag_modal import TagModal
from .ui_elements import BackButton
from ... import config

log = logging.getLogger(__name__)

class TagManagementView(View):
    """标签管理界面的视图"""

    def __init__(self, main_interaction: discord.Interaction):
        super().__init__(timeout=180)
        self.main_interaction = main_interaction
        self.guild_id = main_interaction.guild.id
        
        self.add_item(BackButton())
        self.add_item(AddTagButton())
        self.populate_buttons()

    def populate_buttons(self):
        """从数据库加载标签并创建按钮"""
        # 在重新加载前清除旧的标签按钮
        for item in self.children[:]:
            if isinstance(item, TagButton):
                self.remove_item(item)

        self.tags = db_manager.get_all_tags(self.guild_id)
        for tag in self.tags:
            # 将主视图的引用传递给按钮
            self.add_item(TagButton(tag, parent_view=self))

    @staticmethod
    def get_embed(guild: discord.Guild, tags: list) -> discord.Embed:
        """生成标签管理的 Embed"""
        embed = discord.Embed(
            title="🏷️ 标签管理",
            description="在这里管理用于分类引导路径的标签。\n点击下方按钮新增标签，或点击已有标签进行编辑/删除。",
            color=config.EMBED_COLOR_INFO
        )
        if not tags:
            embed.add_field(name="暂无标签", value="点击“新增标签”来创建第一个标签吧！")
        else:
            tag_list = []
            for tag in tags:
                desc = f"> {tag['description']}" if tag['description'] else "> *无描述*"
                tag_list.append(f"**{tag['tag_name']}**\n{desc}")
            embed.add_field(name="已创建的标签", value="\n\n".join(tag_list), inline=False)
        return embed

    async def refresh(self):
        """
        就地刷新视图和Embed，而不是创建一个新实例。
        """
        # 重新从数据库获取最新的标签列表
        self.tags = db_manager.get_all_tags(self.guild_id)
        
        # 更新Embed
        embed = self.get_embed(self.main_interaction.guild, self.tags)
        
        # 清除旧的标签按钮
        for item in self.children[:]:
            if isinstance(item, TagButton):
                self.remove_item(item)
        
        # 重新添加按钮
        # 注意：需要保持返回和新增按钮在前面
        children_to_keep = [item for item in self.children if not isinstance(item, TagButton)]
        self.clear_items()
        for item in children_to_keep:
            self.add_item(item)
        
        for tag in self.tags:
            self.add_item(TagButton(tag, parent_view=self))

        # 使用原始交互来编辑消息
        await self.main_interaction.edit_original_response(embed=embed, view=self)


# --- 确认删除视图 ---
class ConfirmDeleteView(View):
    def __init__(self, tag: dict, parent_view: 'TagManagementView'):
        super().__init__(timeout=60)
        self.tag = tag
        self.parent_view = parent_view
        self.message: Optional[discord.Message] = None

    @button(label="确认删除", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def confirm_button(self, interaction: discord.Interaction, button: Button):
        try:
            db_manager.delete_tag(self.tag['tag_id'])
            await interaction.response.send_message(f"✅ 成功删除标签 **{self.tag['tag_name']}**。", ephemeral=True)
            await self.parent_view.refresh()
        except Exception as e:
            log.error(f"删除标签失败: {e}", exc_info=True)
            await interaction.response.send_message(f"❌ 删除失败，发生未知错误。", ephemeral=True)
        
        # 停止视图并清理消息
        self.stop()
        if self.message:
            await self.message.delete()

    @button(label="取消", style=discord.ButtonStyle.secondary)
    async def cancel_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        self.stop()
        if self.message:
            await self.message.edit(content="操作已取消。", view=None)


# --- 标签操作视图 ---
class TagActionView(View):
    def __init__(self, tag: dict, parent_view: 'TagManagementView'):
        super().__init__(timeout=180)
        self.tag = tag
        self.parent_view = parent_view

    @button(label="编辑标签", style=discord.ButtonStyle.primary, emoji="✏️", row=0)
    async def edit_button(self, interaction: discord.Interaction, button: Button):
        modal = TagModal(guild_id=interaction.guild.id, existing_tag=self.tag)
        modal.callback_view = self.parent_view
        await interaction.response.send_modal(modal)
        self.stop()

    @button(label="删除标签", style=discord.ButtonStyle.danger, emoji="🗑️", row=0)
    async def delete_button(self, interaction: discord.Interaction, button: Button):
        confirm_view = ConfirmDeleteView(self.tag, self.parent_view)
        msg_content = f"你确定要删除标签 **{self.tag['tag_name']}** 吗？\n> ⚠️ **此操作不可逆**，与此标签关联的所有引导路径也将被删除。"
        await interaction.response.send_message(msg_content, view=confirm_view, ephemeral=True)
        confirm_view.message = await interaction.original_response()
        # This view can be stopped as the user is now interacting with the confirmation view.
        self.stop()

    @button(label="返回列表", style=discord.ButtonStyle.secondary, emoji="↩️", row=1)
    async def back_button(self, interaction: discord.Interaction, button: Button):
        # Defer the interaction response
        await interaction.response.defer()
        # Refresh the parent view, which will edit the message to show the tag list again
        await self.parent_view.refresh()
        self.stop()


# --- 动态生成的按钮 ---
class TagButton(Button):
    def __init__(self, tag: dict, parent_view: 'TagManagementView'):
        super().__init__(label=tag['tag_name'], style=discord.ButtonStyle.primary)
        self.tag = tag
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        # 创建操作视图
        action_view = TagActionView(self.tag, self.parent_view)
        
        # 创建一个新的 embed 来显示正在管理哪个标签
        embed = discord.Embed(
            title=f"管理标签: {self.tag['tag_name']}",
            description=f"你正在管理标签 **{self.tag['tag_name']}**。\n> {self.tag['description'] or '*无描述*'}",
            color=config.EMBED_COLOR_INFO
        )
        
        # 编辑原消息以显示新视图和 embed
        await interaction.response.edit_message(embed=embed, view=action_view)


# --- 固定功能按钮 ---
class AddTagButton(Button):
    def __init__(self):
        super().__init__(label="新增标签", style=discord.ButtonStyle.success, emoji="➕")

    async def callback(self, interaction: discord.Interaction):
        # self.view 是按钮所在的视图实例
        modal = TagModal(guild_id=interaction.guild_id)
        # 将视图的 refresh 方法作为回调传递给 modal
        modal.callback_view = self.view
        await interaction.response.send_modal(modal)