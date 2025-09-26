# -*- coding: utf-8 -*-

"""
存储 Chat 模块相关的非敏感、硬编码的常量。
"""

import os
from src.config import _parse_ids

# --- Chat 功能总开关 ---
CHAT_ENABLED = os.getenv("CHAT_ENABLED", "False").lower() == "true"

# --- Gemini AI 配置 ---
# 定义要使用的 Gemini 模型名称
GEMINI_MODEL = "gemini-flash-latest"

# 用于个人记忆摘要的模型。
SUMMARY_MODEL = "gemini-2.5-flash-lite"

# --- RAG (Retrieval-Augmented Generation) 配置 ---
# 用于查询重写的模型。通常可以使用一个更小、更快的模型来降低成本和延迟。
QUERY_REWRITING_MODEL = "gemini-2.5-flash-lite"


# --- Gemini Service 配置 ---
GEMINI_CHAT_CONFIG = {
    "temperature": 1.1,
    "top_p": 0.97,
    "top_k": 50,
    "max_output_tokens": 3000,
    "thinking_budget": 500,  # 思考预算
}

GEMINI_TEXT_GEN_CONFIG = {
    "temperature": 0.1,
    "max_output_tokens": 200,
}

GEMINI_VISION_GEN_CONFIG = {
    "temperature": 1.1,
    "max_output_tokens": 3000,
}

# 用于生成礼物感谢语的配置
GEMINI_GIFT_GEN_CONFIG = {
    "temperature": 1.1,
    "max_output_tokens": 3000,
}

# 用于生成帖子夸奖的配置
GEMINI_THREAD_PRAISE_CONFIG = {
    "temperature": 1.21,
    "top_p": 0.97,
    "top_k": 40,
    "max_output_tokens": 8192,
}

# 用于生成个人记忆摘要的配置
GEMINI_SUMMARY_GEN_CONFIG = {
    "temperature": 0.5,
    "max_output_tokens": 800,
}

# 用于生成忏悔回应的配置
GEMINI_CONFESSION_GEN_CONFIG = {
    "temperature": 1.1,
    "max_output_tokens": 3000,
}

COOLDOWN_RATES = {
    "default": 2,  # 每分钟请求次数
    "coffee": 5,   # 每分钟请求次数
}
# (min, max) 分钟
BLACKLIST_BAN_DURATION_MINUTES = (3, 8)

# --- API 密钥重试与轮换配置 ---
API_RETRY_CONFIG = {
    "MAX_ATTEMPTS_PER_KEY": 3,  # 单个密钥在因可重试错误而被轮换前，允许的最大尝试次数
    "RETRY_DELAY_SECONDS": 1,   # 对同一个密钥进行重试前的延迟（秒）
}


# --- 类脑币系统 ---
# 在指定论坛频道发帖可获得奖励
COIN_REWARD_FORUM_CHANNEL_IDS = _parse_ids("COIN_REWARD_FORUM_CHANNEL_IDS")

# --- 好感度系统 ---
AFFECTION_CONFIG = {
    "INCREASE_CHANCE": 0.5,       # 每次对话增加好感度的几率
    "INCREASE_AMOUNT": 1,         # 每次增加的点数
    "DAILY_CHAT_AFFECTION_CAP": 20, # 每日通过对话获取的好感度上限
    "BLACKLIST_PENALTY": -5,    # 被AI拉黑时扣除的点数
    "DAILY_FLUCTUATION": (-3, 8)  # 每日好感度随机浮动的范围
}

# --- 投喂功能 ---
FEEDING_CONFIG = {
    "RESPONSE_IMAGE_URL": "https://cdn.discordapp.com/attachments/1403347767912562728/1418576178326802524/3_632830043818943_00001_.png" # 投喂回应的默认图片URL
}

# --- 忏悔功能 ---
CONFESSION_CONFIG = {
    "RESPONSE_IMAGE_URL": "https://cdn.discordapp.com/attachments/1403347767912562728/1419992658067325008/3_1124796593853479_00001_.png" # 忏悔回应的默认图片URL
}

# --- 类脑币系统 ---
COIN_CONFIG = {
    "DAILY_FIRST_CHAT_REWARD": 50, # 每日首次与AI对话获得的类脑币奖励
    "FORUM_POST_REWARD": 200       # 在指定论坛频道发帖获得的类脑币奖励
}

# --- 个人记忆功能 ---
PERSONAL_MEMORY_CONFIG = {
    "summary_threshold": 20,       # 触发总结的消息数量阈值 (测试用 5, 原为 50)
}


# --- 频道记忆功能 ---
CHANNEL_MEMORY_CONFIG = {
    "raw_history_limit": 10,       # 从Discord API获取的原始消息数量
    "formatted_history_limit": 10, # 格式化为AI模型可用的对话历史消息数量
}


# --- Prompt 配置 ---
PROMPT_CONFIG = {
    "personal_memory_summary": (
        "你是一位记忆管理专家。你的核心任务是分析信息，提炼出关于用户的【互动记忆】，而不是记录【具体对话】。\n\n"
        "**最高指令：**\n"
        "**绝对禁止**记录或复述用户的任何具体对话内容。所有记忆点都必须是关于**事件、行为、状态或偏好**的总结。\n"
        "例如：**不要**写“用户说他喜欢玩游戏”，而**应该**写“用户表达了对游戏的热爱”。\n\n"
        "**记忆结构:**\n"
        "请将用户的记忆分为【长期记忆】和【近期动态】两部分。\n\n"
        "**第一部分：【长期记忆】**\n"
        "这部分用于你和用户的长期记忆。规则如下：\n"
        "1.  **提炼核心**: 从所有信息中，总结出 **3-5** 个最重要的记忆点。\n"
        "2.  **保持稳定**: 这些记忆点应该是高度概括且相对稳定的。\n\n"
        "**第二部分：【近期动态】**\n"
        "这部分用于记录最近发生的关键互动与事件。规则如下：\n"
        "1.  **全面提取**: 只从【近期对话】中，提取 **3-5** 个最近发生的、有价值的【关键互动】、【具体事件】或【状态变化】。\n"
        "2.  **禁止复述对话**: 再次强调，这里记录的是**事件**,而不是用户说了什么。\n\n"
        "**通用规则:**\n"
        "- **格式**: 严格按照下面的Markdown格式输出，必须包含两个部分的标题。\n"
        "- **明确主体**: 记录事件时，必须清晰地指明行为的主体是“用户”还是“类脑娘”。例如：“用户对XX表现出兴趣”，“类脑娘对用户的行为作出了XX回应”。\n"
        "- **客观视角**: 所有内容都使用客观第三人称。\n"
        "- **总数限制**: 两部分加起来的总条目数**不得超过15条**。\n\n"
        "**输入材料:**\n"
        "【长期记忆】:\n{old_summary}\n\n"
        "【近期动态】:\n{dialogue_history}\n\n"
        "**请严格遵循以上所有指令，直接开始输出Markdown格式的【全新记忆摘要】，不要包含任何解释、开场白或结束语:**\n"
        "### 长期记忆\n"
        "- (要点1)\n"
        "- (要点2)\n"
        "...\n\n"
        "### 近期动态\n"
        "- (要点1)\n"
        "- (要点2)\n"
        "...\n"
    )
}


# --- Vector DB (ChromaDB) ---
VECTOR_DB_PATH = "data/chroma_db"
VECTOR_DB_COLLECTION_NAME = "world_book"

# --- 世界之书向量化任务配置 ---
WORLD_BOOK_CONFIG = {
    "VECTOR_INDEX_UPDATE_INTERVAL_HOURS": 6,  # 向量索引更新间隔（小时）

    # 审核系统设置
    "review_settings": {
        # 审核的持续时间（分钟）
        "review_duration_minutes": 5,

        # 审核时间结束后，通过所需的最低赞成票数
        "approval_threshold": 5,

        # 在审核期间，可立即通过的赞成票数
        "instant_approval_threshold": 10,

        # 在审核期间，可立即否决的反对票数
        "rejection_threshold": 3,
        
        # 投票使用的表情符号
        "vote_emoji": "✅",
        "reject_emoji": "❌",
    },
    
    # 个人资料审核设置
    "personal_profile_review_settings": {
        # 审核的持续时间（分钟）
        "review_duration_minutes": 5,

        # 审核时间结束后，通过所需的最低赞成票数
        "approval_threshold": 2,

        # 在审核期间，可立即通过的赞成票数
        "instant_approval_threshold": 7,

        # 在审核期间，可立即否决的反对票数
        "rejection_threshold": 3,
        
        # 投票使用的表情符号
        "vote_emoji": "✅",
        "reject_emoji": "❌",
    }
}

# --- 礼物功能提示词配置 ---
GIFT_SYSTEM_PROMPT = """
{persona}
"""

GIFT_PROMPT = """
一个用户刚刚送给你一份礼物。
用户名: {user_name}
礼物: {item_name}
你与该用户当前的好感度等级是: {affection_level}。

根据你的角色设定，写一段3-6句且有吸引力的回复来感谢用户送的礼物。
你的回复应该自然且符合角色设定。
请直接输出回复内容，不要添加任何引导语。
"""

# --- 忏悔功能提示词 ---
CONFESSION_PROMPT = """
{persona}

一个用户刚刚向你忏悔。
用户名: {user_name}
忏悔内容: {confession_message}
你与该用户当前的好感度等级是: {affection_level}。

根据你的角色设定，写一段3-6句的回应。
你的回应应该自然且符合角色设定，可以带有一些俏皮、吐槽或安慰的元素。
在回应的最后，请严格按照以下格式附加上你认为应该奖励的好感度，不要添加任何额外说明：<affection:好感_B度奖励>
好感度奖励范围为 1-20 点。请根据忏悔内容的严重性、真诚度等因素自行判断。
例如：
哼，这点小事就来烦我啦！<affection:+1>
"""

# --- 帖子评价功能 ---
# 功能总开关
THREAD_COMMENTOR_ENABLED = os.getenv("THREAD_COMMENTOR_ENABLED", "False").lower() == "true"
# 指定需要评价的论坛频道ID列表
TARGET_FORUM_CHANNELS = _parse_ids("TARGET_FORUM_CHANNELS")

# --- 调试配置 ---
DEBUG_CONFIG = {
    "LOG_FINAL_CONTEXT": False, # 是否在日志中打印发送给AI的最终上下文，用于调试
    "LOG_AI_FULL_CONTEXT": os.getenv("LOG_AI_FULL_CONTEXT", "False").lower() == "true", # 是否记录AI可见的完整上下文日志
}