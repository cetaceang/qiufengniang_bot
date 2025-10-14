import discord
import aiohttp
from typing import Dict, Any, Optional
from src.chat.features.tools.tool_registry import register_tool

# 为 get_user_avatar 工具定义 Schema
# 注意：我们移除了 parameters，因为 user_id 将从上下文中自动获取。
GET_USER_AVATAR_SCHEMA = {
    "name": "get_user_avatar",
    "description": "当用户询问关于他们自己头像的问题时（例如“我的头像怎么样？”、“看看我的头像”、“评价一下我的- 头像”），调用此工具来获取用户的头像图片",
    "parameters": {
        "type": "object",
        "properties": {}
    }
}

@register_tool(name="get_user_avatar", schema=GET_USER_AVATAR_SCHEMA)
async def get_user_avatar(bot: Optional[discord.Client] = None, author_id: Optional[int] = None) -> Dict[str, Any]:
    """
    get_user_avatar 工具的实现。
    通过 Discord API 获取当前用户的头像，下载图片数据，并将其作为多模态内容返回。

    Args:
        bot: Discord 客户端实例，用于进行 API 调用。
        author_id: 当前用户的 Discord ID，由服务层注入。

    Returns:
        一个包含图片MIME类型和二进制数据的字典，如果失败则返回错误信息。
    """
    if not bot:
        return {"error": "Discord bot instance is not available."}
    if not author_id:
        return {"error": "Author ID was not provided by the service."}

    try:
        user = await bot.fetch_user(author_id)
        if not user or not user.avatar:
            return {"error": f"User with ID {author_id} not found or has no avatar."}

        avatar_url = user.avatar.url
        async with aiohttp.ClientSession() as session:
            async with session.get(str(avatar_url)) as response:
                if response.status == 200:
                    image_bytes = await response.read()
                    # 从URL推断MIME类型，或直接使用常见的默认值
                    mime_type = 'image/png' if 'png' in str(avatar_url) else 'image/jpeg'
                    if 'gif' in str(avatar_url):
                        mime_type = 'image/gif'
                    
                    # 返回一个特殊结构的字典，ToolService将用它来构建多模态响应
                    return {
                        "image_data": {
                            "mime_type": mime_type,
                            "data": image_bytes
                        }
                    }
                else:
                    return {"error": f"Failed to download avatar. Status: {response.status}"}

    except discord.NotFound:
        return {"error": f"User with ID {author_id} not found in Discord."}
    except Exception as e:
        print(f"获取用户 {author_id} 头像时发生未知错误: {e}")
        return {"error": f"An unexpected error occurred while fetching avatar for user ID {author_id}."}
