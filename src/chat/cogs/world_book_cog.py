# -*- coding: utf-8 -*-

import discord
from discord.ext import commands, tasks
import logging
import sqlite3
import os
import json
import re
from datetime import datetime
import asyncio

from src import config
from src.chat.config import chat_config
from src.chat.features.world_book.services.incremental_rag_service import incremental_rag_service
from src.chat.features.personal_memory.services.personal_memory_service import personal_memory_service
from src.chat.features.odysseia_coin.service.coin_service import coin_service

log = logging.getLogger(__name__)

# --- 审核配置 ---
REVIEW_SETTINGS = chat_config.WORLD_BOOK_CONFIG['review_settings']
VOTE_EMOJI = REVIEW_SETTINGS['vote_emoji']
REJECT_EMOJI = REVIEW_SETTINGS['reject_emoji']


class WorldBookCog(commands.Cog):
    """处理世界之书相关功能的Cog，包括条目审核"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db_path = os.path.join(config.DATA_DIR, 'world_book.sqlite3')
        self.check_expired_entries.start()

    def cog_unload(self):
        self.check_expired_entries.cancel()

    def _get_db_connection(self):
        """建立并返回一个新的 SQLite 数据库连接。"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            return conn
        except sqlite3.Error as e:
            log.error(f"连接到世界书数据库失败: {e}", exc_info=True)
            return None

    @commands.Cog.listener('on_raw_reaction_add')
    async def on_review_reaction(self, payload: discord.RawReactionActionEvent):
        """监听对审核消息的反应"""
        # 关键修复：从源头忽略机器人自己的反应事件
        if payload.user_id == self.bot.user.id:
            # log.debug(f"[REACTION_DEBUG] 忽略机器人自己的反应 (User ID: {payload.user_id})")
            return

        # 只处理指定的投票表情
        if str(payload.emoji) not in [VOTE_EMOJI, REJECT_EMOJI]:
            return

        # 确保我们能获取到 Member 对象，以便后续检查
        channel = self.bot.get_channel(payload.channel_id)
        if not isinstance(channel, discord.TextChannel):
            return

        try:
            message = await channel.fetch_message(payload.message_id)
        except discord.NotFound:
            log.warning(f"找不到消息 {payload.message_id}，可能已被删除。")
            return

        if not message.author.id == self.bot.user.id or not message.embeds:
            return

        embed = message.embeds[0]
        # 移除对标题的检查，只依赖 footer 中的审核ID来识别消息
        match = re.search(r"审核ID: (\d+)", embed.footer.text or "")
        if not match:
            return

        pending_id = int(match.group(1))
        log.debug(f"检测到对审核消息 (ID: {message.id}) 的投票，解析出 pending_id: {pending_id}，投票者: {payload.member.display_name}")
        await self.process_vote(pending_id, message)

    def _get_review_settings(self, entry_type: str) -> dict:
        """根据条目类型获取对应的审核配置"""
        if entry_type == 'personal_profile':
            return chat_config.WORLD_BOOK_CONFIG.get('personal_profile_review_settings', REVIEW_SETTINGS)
        return REVIEW_SETTINGS

    async def process_vote(self, pending_id: int, message: discord.Message):
        """处理投票逻辑，检查是否达到阈值"""
        log.debug(f"--- 开始处理投票 for pending_id: {pending_id} ---")
        conn = self._get_db_connection()
        if not conn:
            return

        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM pending_entries WHERE id = ? AND status = 'pending'", (pending_id,))
            entry = cursor.fetchone()

            if not entry:
                log.warning(f"在 process_vote 中找不到待审核的条目 #{pending_id} 或其状态不是 'pending'。")
                return

            review_settings = self._get_review_settings(entry['entry_type'])

            approvals = 0
            rejections = 0
            for reaction in message.reactions:
                if str(reaction.emoji) == review_settings['vote_emoji']:
                    approvals = reaction.count
                elif str(reaction.emoji) == review_settings['reject_emoji']:
                    rejections = reaction.count
            
            instant_approval_threshold = review_settings['instant_approval_threshold']
            log.info(f"审核ID #{pending_id} (类型: {entry['entry_type']}): 当前票数 ✅{approvals}, ❌{rejections}。快速通过阈值: {instant_approval_threshold}")

            if approvals >= instant_approval_threshold:
                log.info(f"审核ID #{pending_id} 达到快速通过阈值。准备批准...")
                await self.approve_entry(pending_id, entry, message, conn)
            elif rejections >= review_settings['rejection_threshold']:
                log.info(f"审核ID #{pending_id} 达到否决阈值。")
                await self.reject_entry(pending_id, entry, message, conn, "社区投票否决")
            else:
                log.info(f"审核ID #{pending_id} 票数未达到任何阈值，等待更多投票或过期。")

        except Exception as e:
            log.error(f"处理投票时发生错误 (ID: {pending_id}): {e}", exc_info=True)
        finally:
            conn.close()

    async def approve_entry(self, pending_id: int, entry: sqlite3.Row, message: discord.Message, conn: sqlite3.Connection):
        """批准条目，将其写入主表并更新状态"""
        try:
            cursor = conn.cursor()
            data = json.loads(entry['data_json'])
            entry_type = entry['entry_type']
            new_entry_id = None
            entry_name = data.get('name', '未知')
            embed_title = "✅ 条目已入库"
            embed_description = f"感谢社区的审核！**{entry_name}** 的贡献已成功添加到世界之书中。"

            if entry_type == 'community_member':
                update_target_id = data.get('update_target_id')
                content_json = json.dumps(data, ensure_ascii=False)

                if update_target_id:
                    cursor.execute(
                        "UPDATE community_members SET title = ?, discord_number_id = ?, content_json = ? WHERE id = ?",
                        (f"社区成员档案 - {data['name']}", data.get('discord_id'), content_json, update_target_id)
                    )
                    new_entry_id = update_target_id
                    log.info(f"已更新社区成员档案 {update_target_id} (源自审核 #{pending_id})。")
                    embed_title = "✅ 社区成员档案已更新"
                else:
                    import time
                    clean_name = re.sub(r'[^\w\u4e00-\u9fff]', '_', data['name'])[:50]
                    member_id = f"community_{clean_name}_{int(time.time())}"
                    cursor.execute(
                        "INSERT INTO community_members (id, title, discord_number_id, content_json, status) VALUES (?, ?, ?, ?, ?)",
                        (member_id, f"社区成员档案 - {data['name']}", data.get('discord_id'), content_json, 'approved')
                    )
                    new_entry_id = member_id
                    log.info(f"已创建新社区成员档案 {new_entry_id} (源自审核 #{pending_id})。")
                    embed_title = "✅ 社区成员档案已入库"

                if data.get('discord_id'):
                    target_user_id = int(data['discord_id'])
                    profile_data = {k: data[k] for k in ['name', 'personality', 'background', 'preferences'] if k in data}
                    asyncio.create_task(personal_memory_service.save_user_profile(target_user_id, profile_data))
                    asyncio.create_task(personal_memory_service.unlock_feature(target_user_id))
                    log.info(f"已为用户 {target_user_id} 绑定/更新个人档案并解锁功能。")

            elif entry_type == 'personal_profile':
                target_user_id = int(data['discord_id'])
                profile_data = {k: data[k] for k in ['name', 'personality', 'background', 'preferences'] if k in data}
                
                await personal_memory_service.save_user_profile(target_user_id, profile_data)
                await personal_memory_service.unlock_feature(target_user_id)
                
                new_entry_id = f"personal_profile_{target_user_id}" # 构造一个唯一的标识符
                log.info(f"已将审核通过的个人档案 #{pending_id} 存入用户 {target_user_id} 的个人记忆中。")
                embed_title = "✅ 个人档案已激活"
                embed_description = f"感谢社区的审核！**{entry_name}** 的个人档案已成功激活。"

            elif entry_type == 'general_knowledge':
                # ... (通用知识逻辑保持不变)
                import time
                category_name = data['category_name']
                cursor.execute("SELECT id FROM categories WHERE name = ?", (category_name,))
                category_row = cursor.fetchone()
                if category_row:
                    category_id = category_row[0]
                else:
                    cursor.execute("INSERT INTO categories (name) VALUES (?)", (category_name,))
                    category_id = cursor.lastrowid
                
                content_dict = {"description": data['content_text']}
                content_json = json.dumps(content_dict, ensure_ascii=False)
                clean_title = re.sub(r'[^\w\u4e00-\u9fff]', '_', data['title'])[:50]
                entry_id = f"{clean_title}_{int(time.time())}"
                
                cursor.execute(
                    "INSERT INTO general_knowledge (id, title, name, content_json, category_id, contributor_id, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))",
                    (entry_id, data['title'], data['name'], content_json, category_id, data.get('contributor_id'), 'approved')
                )
                new_entry_id = entry_id
                log.info(f"已创建通用知识条目 {new_entry_id} (源自审核 #{pending_id})。")
                embed_title = "✅ 世界之书知识已入库"
                embed_description = f"感谢社区的审核！标题为 **{data['title']}** 的贡献已成功添加到世界之书中。"

            if new_entry_id:
                cursor.execute("UPDATE pending_entries SET status = 'approved' WHERE id = ?", (pending_id,))
                conn.commit()
                log.info(f"审核条目 #{pending_id} 状态已更新为 'approved'。")

                if entry_type in ['general_knowledge', 'community_member']:
                    is_update = entry_type == 'community_member' and data.get('update_target_id')
                    rag_id = data['update_target_id'] if is_update else new_entry_id
                    
                    if is_update:
                        log.info(f"为更新的条目 {rag_id} 同步向量...")
                        asyncio.create_task(incremental_rag_service.delete_entry(rag_id))
                        asyncio.create_task(incremental_rag_service.process_community_member(rag_id))
                    elif entry_type == 'community_member':
                        log.info(f"为新社区成员 {rag_id} 创建向量...")
                        asyncio.create_task(incremental_rag_service.process_community_member(rag_id))
                    elif entry_type == 'general_knowledge':
                        log.info(f"为新通用知识 {rag_id} 创建向量...")
                        asyncio.create_task(incremental_rag_service.process_general_knowledge(rag_id))

                original_embed = message.embeds[0]
                new_embed = original_embed.copy()
                new_embed.title = embed_title
                new_embed.description = embed_description
                new_embed.color = discord.Color.green()
                await message.edit(embed=new_embed)
                await message.clear_reactions()
            else:
                log.warning(f"无法识别的条目类型 '{entry_type}' (审核ID: {pending_id})，未执行任何操作。")
                conn.rollback()

        except Exception as e:
            log.error(f"批准条目 #{pending_id} 时出错: {e}", exc_info=True)
            conn.rollback()

    async def _handle_refund(self, entry: sqlite3.Row):
        """处理审核失败的退款逻辑"""
        try:
            data = json.loads(entry['data_json'])
            purchase_info = data.get('purchase_info')

            if not purchase_info:
                log.debug(f"条目 #{entry['id']} 没有购买信息，无需退款。")
                return

            user_id = entry['proposer_id']
            price = purchase_info.get('price')
            item_id = purchase_info.get('item_id')

            if user_id and price is not None:
                await coin_service.add_coins(
                    user_id=user_id,
                    amount=price,
                    reason=f"审核未通过自动退款 (审核ID: {entry['id']}, item_id: {item_id})"
                )
                log.info(f"已为用户 {user_id} 成功退款 {price} 类脑币。")

                # 尝试私信通知用户
                try:
                    user = await self.bot.fetch_user(user_id)
                    embed = discord.Embed(
                        title="【审核结果通知】",
                        description=f"抱歉，您提交的 **{data.get('name', '未知档案')}** 未能通过社区审核。",
                        color=discord.Color.red()
                    )
                    embed.add_field(name="退款通知", value=f"您购买时支付的 **{price}** 类脑币已自动退还到您的账户。")
                    embed.set_footer(text="感谢您的参与！")
                    await user.send(embed=embed)
                    log.info(f"已向用户 {user_id} 发送退款通知。")
                except discord.Forbidden:
                    log.warning(f"无法向用户 {user_id} 发送私信（可能已关闭私信）。")
                except Exception as e:
                    log.error(f"向用户 {user_id} 发送退款通知时出错: {e}", exc_info=True)

        except Exception as e:
            log.error(f"处理退款逻辑时发生严重错误 (审核ID: {entry['id']}): {e}", exc_info=True)

    async def reject_entry(self, pending_id: int, entry: sqlite3.Row, message: discord.Message, conn: sqlite3.Connection, reason: str):
        """否决条目并更新状态"""
        try:
            data = json.loads(entry['data_json'])
            cursor = conn.cursor()
            cursor.execute("UPDATE pending_entries SET status = 'rejected' WHERE id = ?", (pending_id,))
            conn.commit()

            # 更新原始消息
            if message and message.embeds:
                original_embed = message.embeds[0]
                data_name = original_embed.fields[0].value if original_embed.fields else "未知贡献"
                
                new_embed = original_embed.copy()
                # 使标题更通用
                if "档案" in original_embed.title:
                    new_embed.title = f"❌ {data.get('name', '未知')} 的档案"
                    new_embed.description = f"提交未通过审核。\n**原因:** {reason}"
                else:
                    new_embed.title = "❌ 世界之书贡献"
                    new_embed.description = f"标题为 **{data_name}** 的贡献提交未通过审核。\n**原因:** {reason}"

                new_embed.color = discord.Color.red()
                
                await message.edit(embed=new_embed)
                await message.clear_reactions()
            
            log.info(f"审核ID #{pending_id} 已被否决，原因: {reason}")

            # --- 处理退款 ---
            await self._handle_refund(entry)

        except Exception as e:
            log.error(f"否决条目 #{pending_id} 时出错: {e}", exc_info=True)
            conn.rollback()

    @tasks.loop(minutes=1)
    async def check_expired_entries(self):
        """每分钟检查一次已到期的审核条目"""
        await self.bot.wait_until_ready()
        log.debug("开始检查过期的审核条目...")
        
        conn = self._get_db_connection()
        if not conn:
            return

        try:
            cursor = conn.cursor()
            # 找出所有状态为 'pending' 且已过期的条目
            now_iso = datetime.utcnow().isoformat()
            cursor.execute("SELECT * FROM pending_entries WHERE status = 'pending' AND expires_at <= ?", (now_iso,))
            expired_entries = cursor.fetchall()

            if not expired_entries:
                log.debug("没有找到过期的审核条目。")
                return

            log.info(f"找到 {len(expired_entries)} 个过期的审核条目，正在处理...")

            for entry in expired_entries:
                try:
                    channel = self.bot.get_channel(entry['channel_id'])
                    if not channel:
                        log.warning(f"找不到频道 {entry['channel_id']}，无法处理过期条目 #{entry['id']}")
                        continue
                    
                    message = await channel.fetch_message(entry['message_id'])
                    
                    approvals = 0
                    for reaction in message.reactions:
                        if str(reaction.emoji) == VOTE_EMOJI:
                            # 在过期检查中，我们仍然需要排除机器人的初始反应
                            async for user in reaction.users():
                                if not user.bot:
                                    approvals += 1
                            break
                    
                    review_settings = self._get_review_settings(entry['entry_type'])
                    log.info(f"过期审核ID #{entry['id']} (类型: {entry['entry_type']}): 最终真实用户票数 ✅{approvals}。通过阈值: {review_settings['approval_threshold']}")

                    if approvals >= review_settings['approval_threshold']:
                        log.info(f"过期审核ID #{entry['id']} 满足通过条件。")
                        await self.approve_entry(entry['id'], entry, message, conn)
                    else:
                        log.info(f"过期审核ID #{entry['id']} 未满足通过条件。")
                        await self.reject_entry(entry['id'], entry, message, conn, "审核时间结束，票数不足")

                except discord.NotFound:
                    log.warning(f"找不到审核消息 {entry['message_id']}，将直接否决条目 #{entry['id']}")
                    await self.reject_entry(entry['id'], entry, None, conn, "审核消息丢失")
                except Exception as e:
                    log.error(f"处理过期条目 #{entry['id']} 时发生错误: {e}", exc_info=True)

        except Exception as e:
            log.error(f"检查过期条目时发生数据库错误: {e}", exc_info=True)
        finally:
            conn.close()


async def setup(bot: commands.Bot):
    """将这个Cog添加到机器人中"""
    await bot.add_cog(WorldBookCog(bot))