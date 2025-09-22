# -*- coding: utf-8 -*-

import discord
import logging
from typing import Dict, Any

# 导入所需的服务
from src.chat.services.gemini_service import gemini_service
from src.chat.services.context_service import context_service
from src.chat.services.context_service_test import context_service_test # 导入测试服务
from src.chat.features.world_book.services.world_book_service import world_book_service
from src.chat.features.affection.service.affection_service import affection_service
from src.chat.features.odysseia_coin.service.coin_service import coin_service
from src.chat.utils.database import chat_db_manager
from src.chat.features.personal_memory.services.personal_memory_service import personal_memory_service
from src.chat.config.chat_config import PERSONAL_MEMORY_CONFIG, DEBUG_CONFIG

log = logging.getLogger(__name__)

class ChatService:
    """
    负责编排整个AI聊天响应流程。
    """
    async def handle_chat_message(self, message: discord.Message, processed_data: Dict[str, Any]) -> str:
        """
        处理聊天消息，生成并返回AI的最终回复。

        Args:
            message (discord.Message): 原始的 discord 消息对象。
            processed_data (Dict[str, Any]): 由 MessageProcessor 处理后的数据。

        Returns:
            str: AI生成的最终回复文本。如果为 None，则表示不应回复。
        """
        author = message.author
        guild_id = message.guild.id if message.guild else 0

        # --- 个人记忆消息计数 ---
        # --- 个人记忆处理 ---
        user_profile = await chat_db_manager.get_user_profile(author.id)
        personal_summary = None
        has_personal_memory = user_profile and user_profile['has_personal_memory']

        if has_personal_memory:
            personal_summary = user_profile['personal_summary']
            # 在所有对话中进行消息计数和触发总结
            log.debug(f"--- 个人记忆诊断: 用户 {author.id} ---")
            log.debug(f"步骤 1: 检查 has_personal_memory 状态。值为: {has_personal_memory}")
            
            # 在所有对话中进行消息计数和触发总结
            log.debug(f"用户 {author.id} 已启用个人记忆，开始计数。")
            new_count = await personal_memory_service.increment_and_check_message_count(author.id, guild_id)
            log.debug(f"步骤 2: 消息计数器更新。新计数值为: {new_count}")
            
            summary_threshold = PERSONAL_MEMORY_CONFIG['summary_threshold']
            log.debug(f"步骤 3: 检查是否达到阈值。当前计数: {new_count}, 阈值: {summary_threshold}")
            
            if new_count >= summary_threshold:
                log.info(f"用户 {author.id} 在 guild_id {guild_id} 的个人消息已达到 {new_count} 条，触发总结。")
                await personal_memory_service.summarize_and_save_memory(author.id, guild_id)
                await personal_memory_service.reset_message_count(author.id, guild_id)
            else:
                log.debug(f"用户 {author.id} 在 guild_id {guild_id} 的个人消息计数 {new_count} 尚未达到阈值 {summary_threshold}，不触发总结。")
         
        # 移除了对未开启个人记忆的私聊消息的特殊处理

        final_content = processed_data["final_content"]
        image_data_list = processed_data["image_data_list"]

        try:
            # 1. --- 前置检查 ---
            # 检查用户是否被拉黑
            if await chat_db_manager.is_user_blacklisted(author.id, guild_id):
                log.info(f"用户 {author.id} 在服务器 {guild_id} 被拉黑，已跳过。")
                return None

            # 检查冷却状态
            cooldown_type = await coin_service.get_user_cooldown_type(author.id)
            if await gemini_service.is_user_on_cooldown(author.id, cooldown_type):
                log.info(f"用户 {author.id} 处于冷却状态，已跳过。")
                return None

            # 2. --- 上下文与知识库检索 ---
            # 获取频道历史上下文
            # 使用新的测试上下文服务
            channel_context = await context_service_test.get_formatted_channel_history_new(
                message.channel.id, author.id, guild_id, exclude_message_id=message.id
            )

            # RAG: 从世界书检索相关条目
            world_book_entries = await world_book_service.find_entries(
                latest_query=final_content,
                user_id=author.id,
                guild_id=guild_id,
                user_name=author.display_name,
                conversation_history=channel_context
            )

            # 3. --- 好感度与奖励更新（前置） ---
            try:
                # 在生成回复前更新好感度，以确保日志顺序正确
                await affection_service.increase_affection_on_message(author.id, guild_id)
            except Exception as aff_e:
                log.error(f"增加用户 {author.id} 的好感度时出错: {aff_e}")
            
            try:
                # 发放每日首次对话奖励
                if await coin_service.grant_daily_message_reward(author.id):
                    log.info(f"已为用户 {author.id} 发放每日首次对话奖励。")
            except Exception as coin_e:
                log.error(f"为用户 {author.id} 发放每日对话奖励时出错: {coin_e}")

            # 4. --- 调用AI生成回复 ---
            # PromptService 内部会处理合并用户消息的逻辑，这里我们总是传递 final_content
            # --- 构建最终的用户消息 ---
            # 使用新的格式来强化模型的注意力
            final_user_prompt = f"用户名: {author.display_name} 内容: {final_content}"
            
            # 将格式化后的最新用户消息追加到上下文历史的末尾
            channel_context.append({
                "role": "user",
                "parts": [final_user_prompt]
            })
            
            # 记录发送给AI的核心上下文
            if DEBUG_CONFIG["LOG_FINAL_CONTEXT"]:
                log.info(f"发送给AI -> 最终上下文: {channel_context}")
            
            ai_response = await gemini_service.generate_response(
                author.id,
                guild_id,
                message=final_content, # 保持 message 参数用于内部逻辑
                images=image_data_list if image_data_list else None,
                user_name=author.display_name,
                channel_context=channel_context,
                world_book_entries=world_book_entries,
                personal_summary=personal_summary,
                cooldown_type=cooldown_type
            )

            if not ai_response:
                log.info(f"AI服务未返回回复（可能由于冷却），跳过用户 {author.id}。")
                return None

            # 5. --- 后处理与格式化 ---
            final_response = self._format_ai_response(ai_response)
            
            # 6. --- 异步执行后续任务（不阻塞回复） ---
            # 此处现在只应包含不影响核心回复流程的日志记录等任务
            # self._log_rag_summary(author, final_content, world_book_entries, final_response)

            log.info(f"已为用户 {author.display_name} 生成AI回复: {final_response}")
            return final_response

        except Exception as e:
            log.error(f"[ChatService] 处理聊天消息时出错: {e}", exc_info=True)
            return "抱歉，处理你的消息时出现了问题，请稍后再试。"

    def _format_ai_response(self, ai_response: str) -> str:
        """清理和格式化AI的原始回复。"""
        # 移除可能包含的自身名字前缀
        bot_name_prefix = "类脑娘:"
        if ai_response.startswith(bot_name_prefix):
            ai_response = ai_response[len(bot_name_prefix):].lstrip()
        # 将多段回复的双换行符替换为单换行符
        return ai_response.replace('\n\n', '\n')

    async def _perform_post_response_tasks(self, author: discord.User, guild_id: int, query: str, rag_entries: list, response: str):
        """执行发送回复后的任务，如记录日志。"""
        # 好感度和奖励逻辑已前置，此处保留用于未来可能的其他后处理任务
        
        # 记录 RAG 诊断日志
        # self._log_rag_summary(author, query, rag_entries, response)
        pass

    def _log_rag_summary(self, author: discord.User, query: str, entries: list, response: str):
        """生成并记录 RAG 诊断摘要日志。"""
        try:
            if entries:
                doc_details = []
                for entry in entries:
                    distance = entry.get('distance', 'N/A')
                    distance_str = f"{distance:.4f}" if isinstance(distance, (int, float)) else str(distance)
                    content = str(entry.get('content', 'N/A')).replace('\n', '\n    ')
                    doc_details.append(
                        f"  - Doc ID: {entry.get('id', 'N/A')}, Distance: {distance_str}\n"
                        f"    Content: {content}"
                    )
                retrieved_docs_summary = "\n" + "\n".join(doc_details)
            else:
                retrieved_docs_summary = " N/A"

            summary_log_message = (
                f"\n--- RAG DIAGNOSTIC SUMMARY ---\n"
                f"User: {author} ({author.id})\n"
                f"Initial Query: \"{query}\"\n"
                f"Retrieved Docs:{retrieved_docs_summary}\n"
                f"Final AI Response: \"{response}\"\n"
                f"------------------------------"
            )
            log.info(summary_log_message)
        except Exception as log_e:
            log.error(f"生成 RAG 诊断摘要日志时出错: {log_e}")

# 创建一个单例
chat_service = ChatService()