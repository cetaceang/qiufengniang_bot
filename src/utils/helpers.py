# -*- coding: utf-8 -*-

import discord
from typing import Optional, Dict

from .. import config

def create_embed_from_template(
    template_data: Optional[Dict],
    guild: discord.Guild,
    user: Optional[discord.User] = None,
    **kwargs
) -> discord.Embed:
    """一个辅助函数，用于从数据库模板创建功能丰富的 Embed。"""
    if not template_data:
        return discord.Embed(
            title="配置缺失",
            description="管理员尚未配置此消息模板。",
            color=config.EMBED_COLOR_ERROR
        )

    # 准备所有可用的占位符
    format_args = {
        "server_name": guild.name,
        "server_icon": str(guild.icon.url) if guild.icon else None,
        "user_name": user.name if user else "",
        "user_mention": user.mention if user else "",
        "user_avatar": str(user.display_avatar.url) if user else None,
        **kwargs
    }

    # 替换所有文本字段中的占位符
    title = template_data.get("title", "").format(**format_args)
    description = template_data.get("description", "").format(**format_args)
    footer_text = template_data.get("footer_text", "").format(**format_args)
    image_url = template_data.get("image_url", "").format(**format_args)

    # 创建 Embed
    embed = discord.Embed(
        title=title,
        description=description,
        color=config.EMBED_COLOR_INFO
    )

    # 设置页脚 (仅文字)
    if footer_text:
        embed.set_footer(text=footer_text)

    # 设置缩略图 (使用服务器图标)
    if format_args["server_icon"]:
        embed.set_thumbnail(url=format_args["server_icon"])

    # 设置大图
    if image_url:
        embed.set_image(url=image_url)
        
    return embed