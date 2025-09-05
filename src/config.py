# -*- coding: utf-8 -*-

"""
存储项目中的非敏感、硬编码的常量。
"""

import os
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

# --- AI 身份配置 ---
# 用于识别AI自身发布的消息，请在 .env 文件中设置
BRAIN_GIRL_APP_ID = int(os.getenv("BRAIN_GIRL_APP_ID")) if os.getenv("BRAIN_GIRL_APP_ID") else None

# --- Gemini AI 配置 ---
# 定义要使用的 Gemini 模型名称
GEMINI_MODEL = "gemini-2.5-flash"

# --- 类脑币系统 ---
# 在指定论坛频道发帖可获得奖励
COIN_REWARD_FORUM_CHANNEL_IDS = _parse_ids("COIN_REWARD_FORUM_CHANNEL_IDS")

# --- 交互视图相关 ---
VIEW_TIMEOUT = 300  # 交互视图的超时时间（秒），例如按钮、下拉菜单

# --- 好感度系统 ---
AFFECTION_CONFIG = {
    "INCREASE_CHANCE": 0.5,       # 每次对话增加好感度的几率
    "INCREASE_AMOUNT": 0.5,         # 每次增加的点数
    "DAILY_CHAT_AFFECTION_CAP": 10, # 每日通过对话获取的好感度上限
    "BLACKLIST_PENALTY": -10,    # 被AI拉黑时扣除的点数
    "DAILY_FLUCTUATION": (-5, 5)  # 每日好感度随机浮动的范围
}

# --- 类脑币系统 ---
# 在指定论坛频道发帖可获得奖励
COIN_REWARD_FORUM_CHANNEL_IDS = _parse_ids("COIN_REWARD_FORUM_CHANNEL_IDS")
COIN_CONFIG = {
    "DAILY_FIRST_CHAT_REWARD": 10 # 每日首次与AI对话获得的类脑币奖励
}

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
EMBED_COLOR_PRIMARY = 0x49989a # 主要 Embed 颜色

# --- 消息模板 ---
TEMPLATE_TYPES = {
    "welcome_message": {"label": "欢迎消息", "emoji": "👋", "description": "用户获得初始身份组后，收到的第一条私信，引导其选择兴趣标签。", "multiple": True},
    "prompt_message_stage_1": {"label": "一阶段提示消息", "emoji": "👇", "description": "用户选择标签后，在私信中更新的消息，显示第一阶段路径并提供出发按钮。", "multiple": True},
    "welcome_message_stage_2": {"label": "二阶段欢迎消息", "emoji": "✨", "description": "用户获得第二阶段身份组后，收到的私信，告知已解锁新内容。", "multiple": True},
    "completion_message_stage_1": {"label": "一阶段感谢消息", "emoji": "🎉", "description": "用户完成第一阶段所有步骤后收到的消息。", "multiple": True},
    "completion_message_stage_2": {"label": "二阶段感谢消息", "emoji": "💖", "description": "用户完成第二阶段所有步骤后收到的最终感谢消息。", "multiple": True}
}

# --- 引导流程消息 ---
GUIDANCE_COMPLETION_MESSAGE = "🎉 **恭喜！您已完成所有引导！**"