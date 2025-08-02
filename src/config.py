# -*- coding: utf-8 -*-

"""
存储项目中的非敏感、硬编码的常量。
"""

import os
from dotenv import load_dotenv

# 加载 .env 文件中的环境变量
load_dotenv()

def _parse_ids(env_var: str) -> set[int]:
    """从环境变量中解析逗号分隔的 ID 列表"""
    ids_str = os.getenv(env_var)
    if not ids_str:
        return set()
    try:
        # 使用集合推导式来解析、转换并去除重复项
        return {int(id_str.strip()) for id_str in ids_str.split(',') if id_str.strip()}
    except ValueError:
        # 如果转换整数失败，返回空集合。在实际应用中，这里可以添加日志记录。
        return set()

# --- 机器人与服务器配置 ---
# 用于在开发时快速同步命令，请在 .env 文件中设置
GUILD_ID = os.getenv("GUILD_ID")

# --- 权限控制 ---
# 从 .env 文件加载并解析拥有管理权限的用户和角色 ID
DEVELOPER_USER_IDS = _parse_ids("DEVELOPER_USER_IDS")
ADMIN_ROLE_IDS = _parse_ids("ADMIN_ROLE_IDS")

# --- 交互视图相关 ---
VIEW_TIMEOUT = 300  # 交互视图的超时时间（秒），例如按钮、下拉菜单

# --- 用户进度状态 ---
# 用于 user_progress 表中的 status 字段
USER_STATUS_IN_PROGRESS = "in_progress"
USER_STATUS_COMPLETED = "completed"
USER_STATUS_CANCELLED = "cancelled"
USER_STATUS_PENDING_SELECTION = "pending_selection"

# --- 日志相关 ---
LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s - %(message)s"

# --- 路径管理 ---
MAX_PATH_STEPS = 10 # 一条路径最多包含的频道数量

# --- Embed 颜色 ---
EMBED_COLOR_WELCOME = 0x7289DA  # Discord 官方蓝色
EMBED_COLOR_SUCCESS = 0x57F287  # 绿色
EMBED_COLOR_ERROR = 0xED4245    # 红色
EMBED_COLOR_INFO = 0x3E70DD     # 蓝色
EMBED_COLOR_WARNING = 0xFEE75C # 黄色
EMBED_COLOR_PURPLE = 0x9B59B6   # 紫色

# --- 消息模板 ---
TEMPLATE_TYPES = {
   "welcome_message": {"label": "欢迎消息", "emoji": "👋", "description": "用户开始引导时收到的第一条消息。"},
   "prompt_message": {"label": "提示消息", "emoji": "👇", "description": "用户选择兴趣标签后，提示其点击按钮开始的消息。"},
   "final_message": {"label": "最终感谢消息", "emoji": "💖", "description": "用户完成所有引导路径后，收到的最终感谢与总结消息。"}
}

# --- 引导流程消息 ---
GUIDANCE_COMPLETION_MESSAGE = "🎉 **恭喜！您已完成所有引导！**"