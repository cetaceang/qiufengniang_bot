import discord
from discord import Interaction
from typing import Optional

class SettingsModal(discord.ui.Modal, title="频道/分类设置"):
    """用于编辑频道或分类设置的模态窗口。"""

    def __init__(self, entity_name: str, current_config: dict):
        super().__init__()
        self.interaction: Optional[Interaction] = None
        
        # --- 解析当前配置 ---
        cooldown_sec_str = str(current_config.get("cooldown_seconds")) if current_config.get("cooldown_seconds") is not None else ""
        duration_str = str(current_config.get("cooldown_duration")) if current_config.get("cooldown_duration") is not None else ""
        limit_str = str(current_config.get("cooldown_limit")) if current_config.get("cooldown_limit") is not None else ""
        enabled_str = str(current_config.get("is_chat_enabled")).lower() if current_config.get("is_chat_enabled") is not None else ""

        # --- 输入字段定义 ---
        self.enabled_input = discord.ui.TextInput(
            label=f"[{entity_name}] 是否开启聊天",
            placeholder="true / false / 留空以继承",
            default=enabled_str,
            required=False,
            row=0
        )
        
        self.cooldown_seconds_input = discord.ui.TextInput(
            label="--- 固定CD模式 ---",
            placeholder="冷却秒数 (例如: 30)",
            default=cooldown_sec_str,
            required=False,
            row=1
        )

        self.duration_input = discord.ui.TextInput(
            label="--- 频率限制模式 (时间窗口) ---",
            placeholder="时间窗口秒数 (例如: 60)",
            default=duration_str,
            required=False,
            row=2
        )

        self.limit_input = discord.ui.TextInput(
            label="频率限制模式 (次数上限)",
            placeholder="窗口内允许的消息次数 (例如: 2)",
            default=limit_str,
            required=False,
            row=3
        )

        self.add_item(self.enabled_input)
        self.add_item(self.cooldown_seconds_input)
        self.add_item(self.duration_input)
        self.add_item(self.limit_input)

        # --- 用于存储解析结果的属性 ---
        self.is_chat_enabled: Optional[bool] = None
        self.cooldown_seconds: Optional[int] = None
        self.cooldown_duration: Optional[int] = None
        self.cooldown_limit: Optional[int] = None

    async def on_submit(self, interaction: Interaction):
        self.interaction = interaction
        
        try:
            # 解析布尔值
            enabled_val = self.enabled_input.value.strip().lower()
            if enabled_val in ['true', '1', 'yes']:
                self.is_chat_enabled = True
            elif enabled_val in ['false', '0', 'no']:
                self.is_chat_enabled = False
            elif enabled_val == '':
                self.is_chat_enabled = None
            else:
                raise ValueError("无效的布尔值")

            # 解析整数值
            self.cooldown_seconds = int(v) if (v := self.cooldown_seconds_input.value.strip()) else None
            self.cooldown_duration = int(v) if (v := self.duration_input.value.strip()) else None
            self.cooldown_limit = int(v) if (v := self.limit_input.value.strip()) else None

        except (ValueError, TypeError):
            # 如果解析失败，保持属性为 None，让 View 层处理错误提示
            pass

        await interaction.response.defer()
