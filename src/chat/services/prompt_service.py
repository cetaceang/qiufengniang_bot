# -*- coding: utf-8 -*-

import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone, timedelta
from PIL import Image
import io
import json
import re

from google.genai import types

from src.chat.config.prompts import SYSTEM_PROMPT
from src import config
from src.chat.config import chat_config

log = logging.getLogger(__name__)

EMOJI_PLACEHOLDER_REGEX = re.compile(r'__EMOJI_(\w+)__')

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

        # --- 4. 当前用户输入注入---
        current_user_parts = []
        
        # 分离表情图片和附件图片
        emoji_map = {img['name']: img for img in images if img.get('source') == 'emoji'} if images else {}
        attachment_images = [img for img in images if img.get('source') == 'attachment'] if images else []

        # 处理文本和交错的表情图片
        if message:
            last_end = 0
            processed_parts = []

            for match in EMOJI_PLACEHOLDER_REGEX.finditer(message):
                # 1. 添加上一个表情到这个表情之间的文本
                text_segment = message[last_end:match.start()]
                if text_segment:
                    processed_parts.append(text_segment)

                # 2. 添加表情图片
                emoji_name = match.group(1)
                if emoji_name in emoji_map:
                    try:
                        pil_image = Image.open(io.BytesIO(emoji_map[emoji_name]['data']))
                        processed_parts.append(pil_image)
                    except Exception as e:
                        log.error(f"Pillow 无法打开表情图片 {emoji_name}。错误: {e}。")
                
                last_end = match.end()
            
            # 3. 添加最后一个表情后面的文本
            remaining_text = message[last_end:]
            if remaining_text:
                processed_parts.append(remaining_text)
            
            # 4. 为第一个文本部分添加用户名前缀
            if processed_parts:
                # 寻找第一个字符串类型的元素
                first_text_index = -1
                for i, part in enumerate(processed_parts):
                    if isinstance(part, str):
                        first_text_index = i
                        break
                
                # 重构当前用户消息的格式，以符合新的标准
                if first_text_index != -1 and isinstance(processed_parts[first_text_index], str):
                    original_message = processed_parts[first_text_index]
                    
                    # 根据消息内容是否包含换行符（由 message_processor 添加，表示是引用回复）来决定格式
                    if '\n' in original_message:
                        # 如果是回复，用户名和消息之间用换行符
                        formatted_message = f"[{user_name}]:\n{original_message}"
                    else:
                        # 如果是普通消息，则用冒号和空格
                        formatted_message = f"[{user_name}]: {original_message}"
                    
                    processed_parts[first_text_index] = formatted_message

            current_user_parts.extend(processed_parts)

        # 如果没有任何文本，但有附件，添加一个默认的用户标签
        if not message and attachment_images:
            current_user_parts.append(f'用户名:{user_name}, 用户消息:(图片消息)')

        # 追加所有附件图片到末尾
        for img_data in attachment_images:
            try:
                pil_image = Image.open(io.BytesIO(img_data['data']))
                current_user_parts.append(pil_image)
            except Exception as e:
                log.error(f"Pillow 无法打开附件图片。错误: {e}。")
        
        if current_user_parts:
            # Gemini API 不允许连续的 'user' 角色消息。
            # 如果频道历史的最后一条是 'user'，我们需要将当前输入合并进去。
            if final_conversation and final_conversation[-1].get("role") == "user":
                final_conversation[-1]["parts"].extend(current_user_parts)
                log.debug("将当前用户输入合并到上一条 'user' 消息中。")
            else:
                final_conversation.append({"role": "user", "parts": current_user_parts})

        if chat_config.DEBUG_CONFIG["LOG_FINAL_CONTEXT"]:
            log.debug(f"发送给AI的最终提示词: {json.dumps(final_conversation, ensure_ascii=False, indent=2)}")

        return final_conversation

    def _format_world_book_entries(self, entries: Optional[List[Dict]], user_name: str) -> str:
        """将世界书条目列表格式化为独立的知识注入消息。"""
        if not entries:
            return ""

        formatted_entries = []
        for i, entry in enumerate(entries):
            content_value = entry.get('content')
            metadata = entry.get('metadata', {})
            distance = entry.get('distance')

            # 提取内容
            content_str = ""
            if isinstance(content_value, list) and content_value:
                content_str = str(content_value[0])
            elif isinstance(content_value, str):
                content_str = content_value

            # 过滤掉包含“未提供”的行
            filtered_lines = [line for line in content_str.split('\n') if '未提供' not in line]
            if not filtered_lines:
                continue  # 如果过滤后内容为空，则跳过此条目

            final_content = '\n'.join(filtered_lines)

            # 构建条目头部
            header = f"\n\n--- 搜索结果 {i + 1} ---\n"
            
            # 构建元数据部分
            meta_parts = []
            if distance is not None:
                relevance = max(0, 1 - distance)
                meta_parts.append(f"相关性: {relevance:.2%}")
            
            category = metadata.get('category')
            if category:
                meta_parts.append(f"分类: {category}")
            
            source = metadata.get('source')
            if source:
                meta_parts.append(f"来源: {source}")

            meta_str = f"[{' | '.join(meta_parts)}]\n" if meta_parts else ""

            formatted_entries.append(f"{header}{meta_str}{final_content}")

        if formatted_entries:
            # 使用第一个有效条目的ID作为主题，如果找不到则使用通用名称
            main_subject = "相关信息"
            if entries and entries[0].get('id'):
                main_subject = entries[0].get('id')

            header = f"这是关于 '{main_subject}' 的一些记忆，可能与当前对话相关，也可能不相关。请你酌情参考：\n"
            body = "".join(formatted_entries)
            return f"{header}<world_book_context>{body}\n\n</world_book_context>"

        return ""

    def build_rag_summary_prompt(self, latest_query: str, user_name: str, conversation_history: Optional[List[Dict[str, Any]]]) -> str:
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
1. 解析代词: 必须将问题中的代词（如“我”、“我的”、“你”）替换为具体的实体。使用提问者的名字（`{user_name}`）来替换“我”或“我的”。
2. 绝对忠于最新问题: 你的输出必须基于“用户的最新问题”。“对话历史”仅用于补充信息。
3. **仅使用提供的信息**: 严禁使用任何对话历史之外的背景知识或进行联想猜测。
4. 历史无关则直接使用: 如果问题本身已经信息完整且不包含需要解析的代词，就直接使用它，只需做少量清理（如移除语气词）。
5. 保持意图: 不要改变用户原始的查询意图。
6. 简洁明了: 移除无关的闲聊，生成一个清晰、直接的查询。
7. 只输出结果: 你的最终回答只能包含优化后的查询文本，绝对不能包含任何解释、前缀或引号。

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