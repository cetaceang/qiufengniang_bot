# -*- coding: utf-8 -*-

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone, timedelta
from PIL import Image
import io

from google.genai import types

from src.chat.config.prompts import SYSTEM_PROMPT
from src import config

log = logging.getLogger(__name__)

class PromptService:
    """
    负责构建与大语言模型交互所需的各种复杂提示（Prompt）。
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
        构建用于AI聊天的完整对话历史和系统提示。

        Args:
            user_name (str): 用户名。
            message (Optional[str]): 用户当前的消息文本。
            images (Optional[List[Dict]]): 用户当前消息附带的图片。
            channel_context (Optional[List[Dict]]): 频道的历史消息上下文。
            world_book_entries (Optional[List[Dict]]): 从世界书中检索到的相关条目。
            affection_status (Dict[str, Any]): 用户的好感度状态。
            personal_summary (Optional[str]): 用户的个人记忆摘要。

        Returns:
            List[Dict[str, Any]]: 构建完成，可直接发送给 Gemini API 的对话列表。
        """
        # 1. --- 构建动态系统提示 ---
        beijing_tz = timezone(timedelta(hours=8))
        current_beijing_time = datetime.now(beijing_tz).strftime('%Y年%m月%d日 %H:%M')

        world_book_formatted_content = self._format_world_book_entries(world_book_entries)
        subject_name = world_book_entries[0].get('id', '多个主题') if world_book_entries else '对方'
        affection_level_prompt = affection_status.get("prompt", "")

        # 准备个人记忆和频道上下文
        personal_summary_content = f"\n以下是关于用户 {user_name} 的个人记忆，请在对话中参考：\n{personal_summary}\n" if personal_summary else ""
        channel_specific_content = "" # 预留，未来可以从数据库获取频道特定人设

        dynamic_system_prompt = SYSTEM_PROMPT.format(
            current_time=current_beijing_time,
            user_name=user_name,
            world_book_content=world_book_formatted_content,
            affection_level_prompt=affection_level_prompt,
            subject_name=subject_name,
            personal_summary=personal_summary_content,
            channel_specific_context=channel_specific_content
        )

        # 2. --- 初始化对话历史 ---
        final_conversation = [
            {"role": "user", "parts": [dynamic_system_prompt]},
            {"role": "model", "parts": ["好的，我明白了。"]}
        ]

        # 3. --- 合并频道上下文 ---
        if channel_context:
            final_conversation.extend(channel_context)
            log.debug(f"已合并频道上下文，长度为: {len(channel_context)}")

        # 4. --- 处理当前用户输入（文本和图片） ---
        current_user_parts = []
        text_part_content = ""
        if message:
            text_part_content = f'{user_name}: {message}'
        elif images:
            text_part_content = f'{user_name}: (图片消息)'
        
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
        
        # 5. --- 将当前输入追加到对话历史 ---
        if current_user_parts:
            # 如果最后一条消息也是'user'，则将当前消息合并进去，以避免API错误
            if final_conversation and final_conversation[-1].get("role") == "user":
                final_conversation[-1]["parts"].extend(current_user_parts)
            else:
                final_conversation.append({"role": "user", "parts": current_user_parts})

        return final_conversation

    def _format_world_book_entries(self, entries: Optional[List[Dict]]) -> str:
        """将世界书条目列表格式化为字符串。"""
        if not entries:
            return ""
        
        all_contents = []
        for entry in entries:
            content_value = entry.get('content')
            if isinstance(content_value, list) and content_value:
                all_contents.append(str(content_value[0]))
            elif isinstance(content_value, str):
                all_contents.append(content_value)
        
        if all_contents:
            return "<world_book_context>\n" + "\n---\n".join(all_contents) + "\n</world_book_context>"
        
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