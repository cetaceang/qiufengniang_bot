# -*- coding: utf-8 -*-

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone, timedelta
from PIL import Image
import io
import json # 导入 json 模块

from google.genai import types

from src.chat.config.prompts import SYSTEM_PROMPT
from src import config

log = logging.getLogger(__name__)

class PromptService:
    """
    负责构建与大语言模型交互所需的各种复杂提示（Prompt）。
    采用分层注入式结构，动态解析并构建对话历史。
    """

    def build_chat_prompt(
        self,
        user_name: str,
        message: Optional[str],
        images: Optional[List[Dict]],
        channel_context: Optional[List[Dict]],
        world_book_entries: Optional[List[Dict]],
        affection_status: Dict[str, Any],
        personal_summary: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        构建用于AI聊天的分层对话历史。

        此方法将单一的系统提示动态拆分为多个部分，并按顺序注入到对话历史中，
        形成一个结构化的、引导式的上下文，以提高AI的稳定性和可控性。
        """
        final_conversation = []

        # --- 1. 核心身份注入 ---
        # 准备动态填充内容
        beijing_tz = timezone(timedelta(hours=8))
        current_beijing_time = datetime.now(beijing_tz).strftime('%Y年%m月%d日 %H:%M')
        # 动态知识块（世界之书、个人记忆）将作为独立消息注入，无需在此处处理占位符
        core_prompt_template = SYSTEM_PROMPT
        
        # 填充核心提示词
        # 填充核心提示词中真正存在的占位符
        core_prompt = core_prompt_template.format(
            current_time=current_beijing_time,
            user_name=user_name
        )
        
        final_conversation.append({"role": "user", "parts": [core_prompt]})
        final_conversation.append({"role": "model", "parts": ["好的，我是类脑娘，已经准备好了"]})

        # --- 2. 动态知识注入 ---
        # 注入世界之书 (RAG) 内容
        world_book_formatted_content = self._format_world_book_entries(world_book_entries, user_name)
        if world_book_formatted_content:
            final_conversation.append({"role": "user", "parts": [world_book_formatted_content]})
            final_conversation.append({"role": "model", "parts": ["我记下了"]})

        # 注入个人记忆
        if personal_summary:
            personal_summary_content = f"这是关于用户 {user_name} 的一些个人记忆，请在对话中参考：\n<personal_memory>\n{personal_summary}\n</personal_memory>"
            final_conversation.append({"role": "user", "parts": [personal_summary_content]})
            final_conversation.append({"role": "model", "parts": ["关于你的事情，我当然都记得"]})

        # --- 3. 频道历史上下文注入 ---
        if channel_context:
            final_conversation.extend(channel_context)
            log.debug(f"已合并频道上下文，长度为: {len(channel_context)}")

        # --- 4. 当前用户输入注入 ---
        current_user_parts = []
        text_part_content = ""
        if message:
            text_part_content = f'[user]: {user_name}: {message}'
        elif images:
            text_part_content = f'[user]: {user_name}: (图片消息)'
        
        if text_part_content:
            current_user_parts.append(text_part_content)

        if images:
            for i, img_data in enumerate(images):
                image_bytes = img_data.get('data')
                if image_bytes:
                    try:
                        pil_image = Image.open(io.BytesIO(image_bytes))
                        current_user_parts.append(pil_image)
                        log.debug(f"图片附件 {i+1} 成功转换为 PIL.Image 对象。")
                    except Exception as e:
                        log.error(f"Pillow 无法打开图片附件 {i+1}。错误: {e}。")
        
        if current_user_parts:
            # Gemini API 不允许连续的 'user' 角色消息。
            # 如果频道历史的最后一条是 'user'，我们需要将当前输入合并进去。
            if final_conversation and final_conversation[-1].get("role") == "user":
                final_conversation[-1]["parts"].extend(current_user_parts)
                log.debug("将当前用户输入合并到上一条 'user' 消息中。")
            else:
                final_conversation.append({"role": "user", "parts": current_user_parts})

        return final_conversation

    def _format_world_book_entries(self, entries: Optional[List[Dict]], user_name: str) -> str:
        """将世界书条目列表格式化为独立的知识注入消息。"""
        if not entries:
            return ""
        
        all_contents = []
        for entry in entries:
            content_value = entry.get('content')
            if isinstance(content_value, list) and content_value:
                all_contents.append(str(content_value[0]))
            elif isinstance(content_value, str):
                # 过滤掉包含“未提供”的行
                filtered_lines = [line for line in content_value.split('\n') if '未提供' not in line]
                if filtered_lines:
                    all_contents.append('\n'.join(filtered_lines))
        
        if all_contents:
            subject_name = entries[0].get('id', '多个主题')
            header = f"这是关于 '{subject_name}' 的一些记忆，可能与当前对话相关，也可能不相关。请你酌情参考：\n"
            body = "\n---\n".join(all_contents)
            return f"{header}<world_book_context>\n{body}\n</world_book_context>"
        
        return ""

    def build_rag_summary_prompt(self, latest_query: str, user_name: str, conversation_history: Optional[List[Dict[str, any]]]) -> str:
        """
        构建用于生成RAG搜索独立查询的提示。
        """
        history_text = ""
        if conversation_history:
            history_text = "\n".join(
                f'{turn.get("role", "unknown")}: {turn.get("parts", [""])[0]}'
                for turn in conversation_history
                if turn.get("parts") and turn["parts"][0]
            )
        
        if not history_text:
            history_text = "（无相关对话历史）"

        prompt = f"""
你是一个严谨的查询分析助手。你的任务是根据下面提供的“对话历史”作为参考，将“用户的最新问题”改写成一个独立的、信息完整的查询，以便于进行向量数据库搜索。

**核心规则:**
1.  **解析代词**: 必须将问题中的代词（如“我”、“我的”、“你”）替换为具体的实体。使用提问者的名字（`{user_name}`）来替换“我”或“我的”。
2.  **绝对忠于最新问题**: 你的输出必须基于“用户的最新问题”。“对话历史”仅用于补充信息。
3.  **仅使用提供的信息**: **严禁使用任何对话历史之外的背景知识或进行联想猜测。**
4.  **历史无关则直接使用**: 如果问题本身已经信息完整且不包含需要解析的代词，就直接使用它，只需做少量清理（如移除语气词）。
5.  **保持意图**: 不要改变用户原始的查询意图。
6.  **简洁明了**: 移除无关的闲聊，生成一个清晰、直接的查询。
7.  **只输出结果**: 你的最终回答只能包含优化后的查询文本，绝对不能包含任何解释、前缀或引号。

---

**对话历史:**
{history_text}

---

**{user_name} 的最新问题:**
{latest_query}

---

**优化后的查询:**
"""
        return prompt

# 创建一个单例
prompt_service = PromptService()