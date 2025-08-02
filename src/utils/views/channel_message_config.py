# -*- coding: utf-8 -*-

import discord
from discord.ui import View, Button, button, select

from ...utils.database import db_manager
from ...utils.modals.channel_message_modal import ChannelMessageModal
from ...utils.modals.extra_config_modal import ExtraConfigModal
from ... import config
import json

class ChannelMessageConfigView(View):
    """
    管理频道专属消息配置的视图。
    """
    def __init__(self, main_interaction: discord.Interaction):
        super().__init__(timeout=300)
        self.main_interaction = main_interaction
        self.guild = main_interaction.guild
        self.selected_channel_id: int = None
        self.selected_location_is_thread: bool = False

        # 初始化时就添加组件
        self.add_item(self.LocationSelect(self.guild))
        self.update_buttons()

    def update_buttons(self):
        """根据是否选择了频道来更新按钮状态。"""
        # 查找配置、删除按钮并根据是否选择了频道来更新它们的状态
        config_btn = next((item for item in self.children if item.custom_id == "configure_button"), None)
        remove_btn = next((item for item in self.children if item.custom_id == "remove_button"), None)
        extra_btn = next((item for item in self.children if item.custom_id == "extra_config_button"), None)

        is_channel_selected = self.selected_channel_id is not None

        if config_btn:
            config_btn.disabled = not is_channel_selected
        if extra_btn:
            extra_btn.disabled = not is_channel_selected

        if remove_btn:
            config_exists = False
            if is_channel_selected:
                config = db_manager.get_channel_message(self.selected_channel_id)
                if config:
                    config_exists = True
            remove_btn.disabled = not config_exists

    async def get_config_list_embed(self) -> discord.Embed:
        """生成配置列表的 Embed。"""
        embed = discord.Embed(
            title="📝 地点专属消息设置",
            description="在这里为服务器的特定频道或帖子设置独一无二的永久和临时引导消息。\n"
                        "1. **从下方选择一个已在引导路径中配置过的地点**。\n"
                        "2. 点击 **“配置此地点消息”** 来添加或编辑该地点的消息。\n"
                        "3. 点击 **“删除此地点配置”** 来移除该地点的设置。",
            color=config.EMBED_COLOR_INFO
        )

        all_configs = db_manager.get_all_channel_messages(self.guild.id)
        
        if not all_configs:
            embed.add_field(name="当前没有配置", value="点击下方的“添加”按钮开始吧！", inline=False)
        else:
            field_value = ""
            for config_item in all_configs:
                channel = self.guild.get_channel_or_thread(config_item['channel_id'])
                channel_name = channel.name if channel else f"未知地点 (ID: {config_item['channel_id']})"
                
                status = []
                permanent_data = config_item.get('permanent_message_data') or {}
                temporary_data = config_item.get('temporary_message_data') or {}

                if permanent_data:
                    status.append("永久消息")
                if temporary_data:
                    status.append("临时消息")
                if permanent_data.get('image_url'):
                    status.append("🖼️")
                if permanent_data.get('footer'):
                    status.append("📄")
                
                status_str = " | ".join(status) if status else "无内容"
                field_value += f"• **#{channel_name}** - `{status_str}`\n"
            
            if not field_value:
                 field_value = "点击下方的“添加”按钮开始吧！"

            embed.add_field(
                name="已配置的地点",
                value=field_value,
                inline=False
            )

        embed.set_footer(text="选择一个地点后，下方的编辑和删除按钮将启用。")
        return embed

    # --- 组件定义 ---

    class LocationSelect(discord.ui.Select):
        def __init__(self, guild: discord.Guild):
            locations = db_manager.get_configured_path_locations(guild.id)
            options = []
            
            if locations:
                for loc in locations:
                    # 尝试获取频道或帖子对象
                    channel = guild.get_channel_or_thread(loc['location_id'])
                    if channel:
                        # 直接检查从Discord获取的对象的类型，这比依赖数据库中的字符串更可靠
                        is_thread = isinstance(channel, discord.Thread)
                        prefix = "[帖子]" if is_thread else "[频道]"
                        options.append(discord.SelectOption(
                            label=f"{prefix} {channel.name}",
                            value=str(channel.id),
                            description=f"ID: {channel.id}"
                        ))

            if not options:
                options.append(discord.SelectOption(label="没有在路径中配置过的频道/帖子", value="no_locations", emoji="⚠️"))

            super().__init__(
                placeholder="从引导路径中选择一个频道或帖子...",
                min_values=1,
                max_values=1,
                options=options[:25], # 限制最多25个选项
                row=0
            )

        async def callback(self, interaction: discord.Interaction):
            if self.values[0] == "no_locations":
                await interaction.response.send_message("❌ 没有任何频道或帖子在引导路径中被配置。", ephemeral=True)
                return

            await interaction.response.defer()
            self.view.selected_channel_id = int(self.values[0])
            
            # 获取所选对象的类型
            channel = self.view.guild.get_channel_or_thread(self.view.selected_channel_id)
            if channel:
                self.view.selected_location_is_thread = isinstance(channel, discord.Thread)
            else:
                self.view.selected_location_is_thread = False # Fallback

            self.view.update_buttons()
            await self.view.main_interaction.edit_original_response(view=self.view)

    # --- 按钮 ---

    @button(label="配置此地点消息", style=discord.ButtonStyle.primary, emoji="✏️", row=1, disabled=True, custom_id="configure_button")
    async def configure_button(self, interaction: discord.Interaction, button: Button):
        """打开模态框为所选地点添加或编辑配置。"""
        if not self.selected_channel_id:
            await interaction.response.send_message("请先从下拉菜单中选择一个地点。", ephemeral=True)
            return

        # 获取现有配置（可能为 None）
        existing_config = db_manager.get_channel_message(self.selected_channel_id)
        
        # 实例化新的模态框，并传入地点类型
        modal = ChannelMessageModal(
            interaction=interaction,
            channel_id=self.selected_channel_id,
            existing_config=existing_config,
            is_thread=self.selected_location_is_thread
        )
        await interaction.response.send_modal(modal)

        await modal.wait()
        
        # 模态框结束后，刷新视图和 Embed
        self.update_buttons()
        new_embed = await self.get_config_list_embed()
        await self.main_interaction.edit_original_response(embed=new_embed, view=self)

    @button(label="附加设置", style=discord.ButtonStyle.secondary, emoji="✨", row=1, disabled=True, custom_id="extra_config_button")
    async def extra_config_button(self, interaction: discord.Interaction, button: Button):
        """为永久消息设置图片和页脚。"""
        if not self.selected_channel_id:
            await interaction.response.send_message("请先从下拉菜单中选择一个地点。", ephemeral=True)
            return

        config = db_manager.get_channel_message(self.selected_channel_id)
        permanent_data = (config.get('permanent_message_data') or {}) if config else {}
        current_image_url = permanent_data.get('image_url', '')
        current_footer = permanent_data.get('footer', '')

        modal = ExtraConfigModal(current_image_url=current_image_url, current_footer=current_footer)
        await interaction.response.send_modal(modal)
        await modal.wait()

        if modal.submitted_data is not None:
            # 更新 permanent_data 字典
            permanent_data['image_url'] = modal.submitted_data.get('image_url')
            permanent_data['footer'] = modal.submitted_data.get('footer')
            
            # 获取现有的 temporary_data，以防被覆盖
            existing_temporary_data = (config.get('temporary_message_data') or {}) if config else {}

            # 更新或创建配置
            db_manager.set_channel_message(
                guild_id=self.guild.id,
                channel_id=self.selected_channel_id,
                permanent_data=permanent_data,
                temporary_data=existing_temporary_data
            )
            
            await interaction.followup.send("✅ 附加信息已更新。", ephemeral=True)
            
            # 刷新视图
            new_embed = await self.get_config_list_embed()
            await self.main_interaction.edit_original_response(embed=new_embed, view=self)

    @button(label="删除此地点配置", style=discord.ButtonStyle.danger, emoji="🗑️", row=2, disabled=True, custom_id="remove_button")
    async def remove_button(self, interaction: discord.Interaction, button: Button):
        """删除已选地点的配置。"""
        if not self.selected_channel_id:
            await interaction.response.send_message("请先从下拉菜单中选择一个地点。", ephemeral=True)
            return
        
        db_manager.remove_channel_message(self.selected_channel_id)
        
        # 重置选择并刷新
        self.selected_channel_id = None
        self.selected_location_is_thread = False
        self.update_buttons()
        new_embed = await self.get_config_list_embed()
        await self.main_interaction.edit_original_response(embed=new_embed, view=self)
        await interaction.response.send_message(f"✅ 已成功删除该地点的专属消息配置。", ephemeral=True, delete_after=5)

    @button(label="返回主菜单", style=discord.ButtonStyle.grey, emoji="↩️", row=3)
    async def back_button(self, interaction: discord.Interaction, button: Button):
        """返回主管理面板。"""
        from .main_panel import MainPanelView
        await interaction.response.defer()
        embed = MainPanelView.get_main_embed(self.guild)
        view = MainPanelView(self.main_interaction)
        await self.main_interaction.edit_original_response(embed=embed, view=view)