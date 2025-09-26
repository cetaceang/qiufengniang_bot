import discord
from discord.ui import View, Button, Select
from discord import ButtonStyle, SelectOption, Interaction, TextChannel, CategoryChannel, app_commands
from typing import List, Optional, Dict, Any

from src.chat.features.chat_settings.services.chat_settings_service import chat_settings_service
from src.chat.features.chat_settings.ui.channel_settings_modal import SettingsModal
from src.chat.utils.database import chat_db_manager

class ChatSettingsView(View):
    """聊天设置的主UI面板"""

    def __init__(self, interaction: Interaction):
        super().__init__(timeout=300)
        self.guild = interaction.guild
        self.service = chat_settings_service
        self.settings: Dict[str, Any] = {}
        self.message: Optional[discord.Message] = None

    async def _initialize(self):
        """异步获取设置并构建UI。"""
        self.settings = await self.service.get_guild_settings(self.guild.id)
        self._create_view_items()

    @classmethod
    async def create(cls, interaction: Interaction):
        """工厂方法，用于异步创建和初始化View。"""
        view = cls(interaction)
        await view._initialize()
        return view

    def _create_view_items(self):
        """根据当前设置创建并添加所有UI组件。"""
        self.clear_items()

        # 全局开关
        global_chat_enabled = self.settings.get("global", {}).get("chat_enabled", True)
        self.add_item(Button(
            label=f"聊天总开关: {'开' if global_chat_enabled else '关'}",
            style=ButtonStyle.green if global_chat_enabled else ButtonStyle.red,
            custom_id="global_chat_toggle"
        ))

        warm_up_enabled = self.settings.get("global", {}).get("warm_up_enabled", True)
        self.add_item(Button(
            label=f"暖贴功能: {'开' if warm_up_enabled else '关'}",
            style=ButtonStyle.green if warm_up_enabled else ButtonStyle.red,
            custom_id="warm_up_toggle"
        ))
        
        # 分类选择器
        category_options = [SelectOption(label=c.name, value=str(c.id)) for c in self.guild.categories]
        if category_options:
            self.add_item(Select(placeholder="选择一个分类进行设置...", options=category_options, custom_id="category_select"))

        # 频道选择器
        channel_options = [SelectOption(label=c.name, value=str(c.id)) for c in self.guild.text_channels]
        if channel_options:
            self.add_item(Select(placeholder="选择一个频道进行设置...", options=channel_options[:25], custom_id="channel_select"))

    async def _update_view(self):
        """通过编辑附加的消息来刷新视图。"""
        await self._initialize()
        if self.message:
            await self.message.edit(content="设置已更新。", view=self)

    async def interaction_check(self, interaction: Interaction) -> bool:
        """统一处理所有组件的交互"""
        custom_id = interaction.data.get("custom_id")

        if custom_id == "global_chat_toggle":
            await self.on_global_toggle(interaction)
        elif custom_id == "warm_up_toggle":
            await self.on_warm_up_toggle(interaction)
        elif custom_id == "category_select":
            await self.on_category_select(interaction)
        elif custom_id == "channel_select":
            await self.on_channel_select(interaction)
            
        return True # 返回True表示交互已处理

    async def on_global_toggle(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        current_state = self.settings.get("global", {}).get("chat_enabled", True)
        new_state = not current_state
        await self.service.db_manager.update_global_chat_config(self.guild.id, chat_enabled=new_state)
        await self._update_view()

    async def on_warm_up_toggle(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        current_state = self.settings.get("global", {}).get("warm_up_enabled", True)
        new_state = not current_state
        await self.service.db_manager.update_global_chat_config(self.guild.id, warm_up_enabled=new_state)
        await self._update_view()

    async def on_category_select(self, interaction: Interaction):
        entity_id = int(interaction.data['values'][0])
        entity = self.guild.get_channel(entity_id)
        if not entity:
            await interaction.response.send_message("找不到该分类。", ephemeral=True)
            return

        current_config = self.settings.get("channels", {}).get(entity_id, {})
        modal = SettingsModal(entity_name=entity.name, current_config=current_config)
        await interaction.response.send_modal(modal)
        await modal.wait()
        
        if modal.interaction:
            await self._handle_modal_submit(modal.interaction, entity_id, "category", modal)

    async def on_channel_select(self, interaction: Interaction):
        entity_id = int(interaction.data['values'][0])
        entity = self.guild.get_channel(entity_id)
        if not entity:
            await interaction.response.send_message("找不到该频道。", ephemeral=True)
            return

        current_config = self.settings.get("channels", {}).get(entity_id, {})
        modal = SettingsModal(entity_name=entity.name, current_config=current_config)
        await interaction.response.send_modal(modal)
        await modal.wait()

        if modal.interaction:
            await self._handle_modal_submit(modal.interaction, entity_id, "channel", modal)

    async def _handle_modal_submit(self, interaction: Interaction, entity_id: int, entity_type: str, modal: SettingsModal):
        """处理模态窗口提交的数据并保存。"""
        try:
            # 从 modal 实例中直接获取解析好的值
            await self.service.set_entity_settings(
                guild_id=self.guild.id,
                entity_id=entity_id,
                entity_type=entity_type,
                is_chat_enabled=modal.is_chat_enabled,
                cooldown_seconds=modal.cooldown_seconds,
                cooldown_duration=modal.cooldown_duration,
                cooldown_limit=modal.cooldown_limit
            )

            entity = self.guild.get_channel(entity_id)
            entity_name = entity.name if entity else f"ID: {entity_id}"

            # 构建更详细的反馈信息
            enabled_str = "继承"
            if modal.is_chat_enabled is True: enabled_str = "✅ 开启"
            if modal.is_chat_enabled is False: enabled_str = "❌ 关闭"

            cd_sec_str = f"{modal.cooldown_seconds} 秒" if modal.cooldown_seconds is not None else "继承"
            
            freq_str = "继承"
            if modal.cooldown_duration is not None and modal.cooldown_limit is not None:
                freq_str = f"{modal.cooldown_duration} 秒内最多 {modal.cooldown_limit} 次"

            feedback = (
                f"✅ 已成功为 **{entity_name}** ({entity_type}) 更新设置。\n"
                f"🔹 **聊天总开关**: {enabled_str}\n"
                f"🔹 **固定冷却(秒)**: {cd_sec_str}\n"
                f"🔹 **频率限制**: {freq_str}"
            )

            await interaction.followup.send(feedback, ephemeral=True)
            await self._update_view()

        except Exception as e:
            await interaction.followup.send(f"❌ 保存设置时出错: {e}", ephemeral=True)