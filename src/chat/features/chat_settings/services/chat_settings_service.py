import discord
from typing import Optional, Dict, Any
from datetime import datetime, timedelta, timezone
from src.chat.utils.database import chat_db_manager

class ChatSettingsService:
    """封装聊天设置相关的所有业务逻辑。"""

    def __init__(self):
        self.db_manager = chat_db_manager

    async def set_entity_settings(self, guild_id: int, entity_id: int, entity_type: str,
                                  is_chat_enabled: Optional[bool],
                                  cooldown_seconds: Optional[int],
                                  cooldown_duration: Optional[int],
                                  cooldown_limit: Optional[int]):
        """设置频道或分类的聊天配置，支持所有CD模式。"""
        await self.db_manager.update_channel_config(
            guild_id=guild_id,
            entity_id=entity_id,
            entity_type=entity_type,
            is_chat_enabled=is_chat_enabled,
            cooldown_seconds=cooldown_seconds,
            cooldown_duration=cooldown_duration,
            cooldown_limit=cooldown_limit
        )

    async def get_guild_settings(self, guild_id: int) -> Dict[str, Any]:
        """获取一个服务器的完整聊天设置，包括全局和所有特定频道的配置。"""
        global_config_row = await self.db_manager.get_global_chat_config(guild_id)
        channel_configs_rows = await self.db_manager.get_all_channel_configs_for_guild(guild_id)

        settings = {
            "global": {
                "chat_enabled": global_config_row['chat_enabled'] if global_config_row else True,
                "warm_up_enabled": global_config_row['warm_up_enabled'] if global_config_row else True,
            },
            "channels": {
                config['entity_id']: {
                    "entity_type": config['entity_type'],
                    "is_chat_enabled": config['is_chat_enabled'],
                    "cooldown_seconds": config['cooldown_seconds'],
                    "cooldown_duration": config['cooldown_duration'],
                    "cooldown_limit": config['cooldown_limit'],
                } for config in channel_configs_rows
            }
        }
        return settings

    async def is_chat_globally_enabled(self, guild_id: int) -> bool:
        """检查聊天功能是否在服务器内全局开启。"""
        config = await self.db_manager.get_global_chat_config(guild_id)
        return config['chat_enabled'] if config else True

    async def is_warm_up_enabled(self, guild_id: int) -> bool:
        """检查暖贴功能是否开启。"""
        config = await self.db_manager.get_global_chat_config(guild_id)
        return config['warm_up_enabled'] if config else True
        
    async def get_effective_channel_config(self, channel: discord.abc.GuildChannel) -> Dict[str, Any]:
        """
        获取频道的最终生效配置。
        优先级: 帖子主人设置 > 频道特定设置 > 分类设置 > 全局默认
        """
        guild_id = channel.guild.id
        channel_id = channel.id
        channel_category_id = channel.category_id if hasattr(channel, 'category_id') else None

        # 默认配置
        effective_config = {
            "is_chat_enabled": True,
            "cooldown_seconds": 0,
            "cooldown_duration": None,
            "cooldown_limit": None
        }

        # 1. 获取分类配置
        category_config = None
        if channel_category_id:
            category_config = await self.db_manager.get_channel_config(guild_id, channel_category_id)
        
        if category_config:
            if category_config['is_chat_enabled'] is not None:
                effective_config['is_chat_enabled'] = category_config['is_chat_enabled']
            if category_config['cooldown_seconds'] is not None:
                effective_config['cooldown_seconds'] = category_config['cooldown_seconds']
            if category_config['cooldown_duration'] is not None:
                effective_config['cooldown_duration'] = category_config['cooldown_duration']
            if category_config['cooldown_limit'] is not None:
                effective_config['cooldown_limit'] = category_config['cooldown_limit']

        # 2. 获取频道特定配置，并覆盖分类配置
        channel_config = await self.db_manager.get_channel_config(guild_id, channel_id)
        if channel_config:
            if channel_config['is_chat_enabled'] is not None:
                effective_config['is_chat_enabled'] = channel_config['is_chat_enabled']
            if channel_config['cooldown_seconds'] is not None:
                effective_config['cooldown_seconds'] = channel_config['cooldown_seconds']
            if channel_config['cooldown_duration'] is not None:
                effective_config['cooldown_duration'] = channel_config['cooldown_duration']
            if channel_config['cooldown_limit'] is not None:
                effective_config['cooldown_limit'] = channel_config['cooldown_limit']
        
        # 3. 如果是帖子，获取并应用帖子主人的个人设置 (最高优先级)
        if isinstance(channel, discord.Thread) and channel.owner_id:
            owner_id = channel.owner_id
            query = "SELECT thread_cooldown_seconds, thread_cooldown_duration, thread_cooldown_limit FROM user_coins WHERE user_id = ?"
            owner_config_row = await self.db_manager._execute(self.db_manager._db_transaction, query, (owner_id,), fetch="one")

            if owner_config_row:
                # 个人设置不包含 is_chat_enabled，只覆盖CD
                has_personal_fixed_cd = owner_config_row['thread_cooldown_seconds'] is not None
                has_personal_freq_cd = owner_config_row['thread_cooldown_duration'] is not None and owner_config_row['thread_cooldown_limit'] is not None

                if has_personal_fixed_cd:
                    effective_config['cooldown_seconds'] = owner_config_row['thread_cooldown_seconds']
                    effective_config['cooldown_duration'] = None
                    effective_config['cooldown_limit'] = None
                elif has_personal_freq_cd:
                    effective_config['cooldown_seconds'] = 0
                    effective_config['cooldown_duration'] = owner_config_row['thread_cooldown_duration']
                    effective_config['cooldown_limit'] = owner_config_row['thread_cooldown_limit']

        return effective_config

    async def is_user_on_cooldown(self, user_id: int, channel_id: int, config: Dict[str, Any]) -> bool:
        """
        根据提供的配置，智能检查用户是否处于冷却状态。
        优先使用频率限制模式，否则回退到固定时长模式。
        """
        duration = config.get("cooldown_duration")
        limit = config.get("cooldown_limit")
        cooldown_seconds = config.get("cooldown_seconds")

        # --- 模式1: 频率限制 ---
        if duration is not None and limit is not None and duration > 0 and limit > 0:
            timestamps = await self.db_manager.get_user_timestamps_in_window(user_id, channel_id, duration)
            return len(timestamps) >= limit

        # --- 模式2: 固定时长 ---
        if cooldown_seconds is not None and cooldown_seconds > 0:
            last_message_row = await self.db_manager.get_user_cooldown(user_id, channel_id)
            if not last_message_row or not last_message_row['last_message_timestamp']:
                return False
            
            last_message_time = datetime.fromisoformat(last_message_row['last_message_timestamp']).replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) < last_message_time + timedelta(seconds=cooldown_seconds):
                return True
        
        return False

    async def update_user_cooldown(self, user_id: int, channel_id: int, config: Dict[str, Any]):
        """
        根据当前生效的CD模式，更新用户的冷却记录。
        """
        duration = config.get("cooldown_duration")
        limit = config.get("cooldown_limit")

        # 如果是频率限制模式，则添加时间戳
        if duration is not None and limit is not None and duration > 0 and limit > 0:
            await self.db_manager.add_user_timestamp(user_id, channel_id)
        
        # 总是更新固定CD的时间戳，以备模式切换或用于其他目的
        await self.db_manager.update_user_cooldown(user_id, channel_id)

# 单例实例
chat_settings_service = ChatSettingsService()