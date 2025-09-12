# -*- coding: utf-8 -*-

"""
存储 Chat 模块相关的非敏感、硬编码的常量。
"""

import os
from src.config import _parse_ids

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
    "top_p": 0.99,
    "top_k": 60,
    "max_output_tokens": 400,
}

GEMINI_TEXT_GEN_CONFIG = {
    "temperature": 0.1,
    "max_output_tokens": 200,
}

COOLDOWN_RATES = {
    "default": 2,  # 每分钟请求次数
    "coffee": 5,   # 每分钟请求次数
}

# (min, max) 分钟
BLACKLIST_BAN_DURATION_MINUTES = (5, 10)


# --- 类脑币系统 ---
# 在指定论坛频道发帖可获得奖励
COIN_REWARD_FORUM_CHANNEL_IDS = _parse_ids("COIN_REWARD_FORUM_CHANNEL_IDS")

# --- 好感度系统 ---
AFFECTION_CONFIG = {
    "INCREASE_CHANCE": 0.5,       # 每次对话增加好感度的几率
    "INCREASE_AMOUNT": 0.5,         # 每次增加的点数
    "DAILY_CHAT_AFFECTION_CAP": 10, # 每日通过对话获取的好感度上限
    "BLACKLIST_PENALTY": -10,    # 被AI拉黑时扣除的点数
    "DAILY_FLUCTUATION": (-5, 5)  # 每日好感度随机浮动的范围
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
        "你是一个信息总结专家。请为以下对话历史生成一份高度概括的、要点式的摘要。\n\n"
        "要求：\n"
        "1. 摘要必须采用列表的格式。\n"
        "2. 每条摘要都应极其简练，只保留最核心的信息。\n"
        "3. 重点关注用户的核心观点、情绪变化、以及明确提出的需求或问题。\n"
        "4. 总结的条目总数不应超过10条。\n"
        "5. 使用第三人称视角进行客观陈述。\n\n"
        "对话历史：\n{dialogue_history}\n\n"
        "摘要：\n"
    )
}


# --- Vector DB (ChromaDB) ---
VECTOR_DB_PATH = "data/chroma_db"
VECTOR_DB_COLLECTION_NAME = "world_book"

# --- 世界之书向量化任务配置 ---
WORLD_BOOK_CONFIG = {
    "VECTOR_INDEX_UPDATE_INTERVAL_HOURS": 6  # 向量索引更新间隔（小时）
}