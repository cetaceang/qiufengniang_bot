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
GEMINI_MODEL = "gemini-2.5-flash"

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
    "max_output_tokens": 2000,
}

# 用于生成个人记忆摘要的配置
GEMINI_SUMMARY_GEN_CONFIG = {
    "temperature": 0.5,
    "max_output_tokens": 2000,
}

COOLDOWN_RATES = {
    "default": 2,  # 每分钟请求次数
    "coffee": 5,   # 每分钟请求次数
}

# (min, max) 分钟
BLACKLIST_BAN_DURATION_MINUTES = (3, 8)


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
        "你是一个严谨的记忆史官，你的唯一任务是记录和延续，而非创造或总结。\n"
        "你将收到【过往记忆】和【近期对话】。你的工作是生成一份【全新记忆】，这份新记忆必须遵循以下铁律：\n\n"
        "**铁律一：绝对保留**\n"
        "【过往记忆】中的所有条目，必须一字不差、按原顺序完整地复制到【全新记忆】的开头。\n\n"
        "**铁律二：时序追加**\n"
        "从【近期对话】中提取新的、有价值的记忆点，作为新的列表项，**追加**到内容的**末尾**。\n\n"
        "**铁律三：客观记录**\n"
        "所有记忆点都必须使用客观的第三人称（例如“该用户...”、“他/她...”）。\n\n"
        "**格式要求**\n"
        "使用 Markdown 的无序列表 (`- `) 格式。\n\n"
        "**输入内容:**\n"
        "【过往记忆】:\n{old_summary}\n\n"
        "【近期对话】:\n{dialogue_history}\n\n"
        "**请严格遵循铁律，生成【全新记忆】:**\n"
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