# -*- coding: utf-8 -*-

import discord
from discord.ui import Modal, TextInput
import logging
from typing import Dict, Any, Optional, Union

# 从我们自己的模块中导入
from utils.database import db_manager

log = logging.getLogger(__name__)

class PanelConfigModal(Modal, title="引导面板内容配置"):
    """
    一个模态窗口，用于收集管理员对引导面板和临时消息的配置。
    """
    # --- 永久引导面板的输入框 ---
    panel_title = TextInput(
        label="面板标题",
        placeholder="例如：欢迎来到本频道！",
        required=True,
        max_length=256
    )
    panel_description = TextInput(
        label="面板描述内容",
        style=discord.TextStyle.long,
        placeholder="在这里详细介绍这个频道/帖子是做什么的，有什么规则...",
        required=True,
        max_length=4000
    )
    panel_color = TextInput(
        label="面板侧边栏颜色 (Hex格式)",
        placeholder="例如：#3498db (蓝色), 留空则为默认",
        required=False,
        max_length=7
    )

    def __init__(self, location: Union[discord.TextChannel, discord.Thread], existing_config: Optional[Dict] = None):
        super().__init__()
        self.location = location
        
        # 如果有现有配置，则填充模态窗口的默认值
        if existing_config:
            self.panel_title.default = existing_config.get('title')
            self.panel_description.default = existing_config.get('description')
            # 将整数颜色转换回 Hex 字符串
            color_int = existing_config.get('color')
            if color_int:
                self.panel_color.default = f"#{color_int:06x}"

    async def on_submit(self, interaction: discord.Interaction):
        """当用户提交模态窗口时被调用"""
        if not interaction.guild_id:
            return
            
        try:
            # 1. 处理颜色输入
            raw_color = self.panel_color.value
            color_value = 0x2F3136 # 默认颜色
            if raw_color:
                if raw_color.startswith('#'):
                    raw_color = raw_color[1:]
                try:
                    color_value = int(raw_color, 16)
                except ValueError:
                    await interaction.response.send_message("⚠️ 颜色代码格式不正确，请使用 `#RRGGBB` 或 `RRGGBB` 格式。将使用默认颜色。", ephemeral=True)
            
            # 2. 构建要存入数据库的字典
            panel_embed_data = {
                "title": self.panel_title.value,
                "description": self.panel_description.value,
                "color": color_value
            }

            # 3. 确定位置类型
            location_type = 'THREAD' if isinstance(self.location, discord.Thread) else 'CHANNEL'

            # 4. 保存到数据库
            db_manager.set_panel_config(
                guild_id=interaction.guild_id,
                location_id=self.location.id,
                location_type=location_type,
                panel_data=panel_embed_data
            )

            log.info(f"面板配置已为 {location_type} {self.location.name} (ID: {self.location.id}) 保存。")

            # 5. 回复用户
            embed = discord.Embed(
                title="✅ 面板配置已保存",
                description=f"你已经成功设置了 {self.location.mention} 的引导面板信息。\n\n"
                            f"现在，请在该位置使用 `/新人引导设置 部署引导面板` 命令来让面板生效。",
                color=color_value
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            log.error(f"处理面板配置模态窗口时出错: {e}", exc_info=True)
            await interaction.response.send_message("❌ 保存配置时发生严重错误，请联系机器人管理员。", ephemeral=True)

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        log.error(f"面板配置模态窗口发生错误: {error}", exc_info=True)
        await interaction.response.send_message("❌ 模态窗口发生未知错误，操作未完成。", ephemeral=True)