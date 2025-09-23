import discord
import logging
import json
import sqlite3
import os
from typing import Dict, Any
from datetime import datetime, timedelta

from src import config
from src.chat.config import chat_config
from src.chat.features.world_book.services.incremental_rag_service import incremental_rag_service
import asyncio
import re

log = logging.getLogger(__name__)

# 定义可用的类别列表

# 获取审核配置
REVIEW_SETTINGS = chat_config.WORLD_BOOK_CONFIG['review_settings']
VOTE_EMOJI = REVIEW_SETTINGS['vote_emoji']
REJECT_EMOJI = REVIEW_SETTINGS['reject_emoji']
AVAILABLE_CATEGORIES = [
    "社区信息",
    "社区文化",
    "社区大事件",
    "俚语",
    "社区知识"
]

class WorldBookContributionModal(discord.ui.Modal, title="贡献知识"):
    """用于用户提交世界书知识条目的模态窗口"""
    
    def __init__(self, purchase_info: Dict[str, Any] = None):
        super().__init__()
        self.purchase_info = purchase_info
        
        self.category_input = discord.ui.TextInput(
            label="类别",
            placeholder=f"请输入类别，例如：{', '.join(AVAILABLE_CATEGORIES)}",
            max_length=50,
            required=True
        )
        self.add_item(self.category_input)
        
        self.title_input = discord.ui.TextInput(
            label="标题",
            placeholder="请输入知识条目的标题",
            max_length=100,
            required=True
        )
        self.add_item(self.title_input)
        
        self.content_input = discord.ui.TextInput(
            label="内容",
            placeholder="请输入详细内容",
            style=discord.TextStyle.paragraph,
            max_length=2000,
            required=True
        )
        self.add_item(self.content_input)

    def _get_world_book_connection(self):
        """获取世界书数据库的连接"""
        try:
            db_path = os.path.join(config.DATA_DIR, 'world_book.sqlite3')
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            return conn
        except sqlite3.Error as e:
            log.error(f"连接到世界书数据库失败: {e}", exc_info=True)
            return None

    async def create_pending_entry(self, interaction: discord.Interaction, knowledge_data: Dict[str, Any]) -> int | None:
        """将提交的数据作为待审核条目存入数据库"""
        conn = self._get_world_book_connection()
        if not conn:
            return None
            
        try:
            cursor = conn.cursor()
            
            duration_minutes = chat_config.WORLD_BOOK_CONFIG['review_settings']['review_duration_minutes']
            expires_at = datetime.utcnow() + timedelta(minutes=duration_minutes)
            
            data_json = json.dumps(knowledge_data, ensure_ascii=False)
            
            cursor.execute("""
                INSERT INTO pending_entries
                (entry_type, data_json, channel_id, guild_id, proposer_id, expires_at, message_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                'general_knowledge',
                data_json,
                interaction.channel_id,
                interaction.guild_id,
                interaction.user.id,
                expires_at.isoformat(),
                -1 # 临时 message_id
            ))
            
            pending_id = cursor.lastrowid
            conn.commit()
            log.info(f"已创建待审核条目 #{pending_id} (类型: general_knowledge)，提交者: {interaction.user.id}")
            return pending_id
            
        except sqlite3.Error as e:
            log.error(f"创建待审核条目时发生数据库错误: {e}", exc_info=True)
            conn.rollback()
            return None
        finally:
            conn.close()

    async def update_message_id_for_pending_entry(self, pending_id: int, message_id: int):
        """更新待审核条目的 message_id"""
        conn = self._get_world_book_connection()
        if not conn:
            return

        try:
            cursor = conn.cursor()
            cursor.execute("UPDATE pending_entries SET message_id = ? WHERE id = ?", (message_id, pending_id))
            conn.commit()
            log.info(f"已为待审核条目 #{pending_id} 更新 message_id 为 {message_id}")
        except sqlite3.Error as e:
            log.error(f"更新待审核条目的 message_id 时出错: {e}", exc_info=True)
            conn.rollback()
        finally:
            conn.close()

    async def on_submit(self, interaction: discord.Interaction):
        """当用户提交模态窗口时调用"""
        # --- 如果是通过商店购买，先处理扣款 ---
        if self.purchase_info:
            await interaction.response.defer(ephemeral=True) # 延迟响应以处理扣款
            from src.chat.features.odysseia_coin.service.coin_service import coin_service
            
            price = self.purchase_info.get('price', 0)
            item_id = self.purchase_info.get('item_id')

            # 只有在价格大于0时才执行扣款
            if price > 0:
                new_balance = await coin_service.remove_coins(
                    user_id=interaction.user.id,
                    amount=price,
                    reason=f"购买知识纸条 (item_id: {item_id})"
                )
                
                if new_balance is None:
                    await interaction.followup.send("抱歉，你的余额似乎不足，购买失败。", ephemeral=True)
                    return
        # --- 扣款逻辑结束 ---

        category = self.category_input.value.strip()
        title = self.title_input.value.strip()
        content = self.content_input.value.strip()

        # 根据是否已延迟响应，选择正确的发送方法
        responder = interaction.followup.send if interaction.response.is_done() else interaction.response.send_message

        if category not in AVAILABLE_CATEGORIES:
            await responder(f"无效的类别。请从以下选项中选择: {', '.join(AVAILABLE_CATEGORIES)}", ephemeral=True)
            return

        if not all([category, title, content]):
            await responder("类别、标题和内容均不能为空。", ephemeral=True)
            return

        # --- 开发者后门逻辑 ---
        if interaction.user.id in config.DEVELOPER_USER_IDS:
            await self.developer_direct_add(interaction, category, title, content)
            return
        # --- 结束 ---

        knowledge_data = {
            'category_name': category,
            'title': title,
            'name': title, # 使用标题作为名称
            'content_text': content,
            'contributor_id': interaction.user.id,
            'contributor_name': interaction.user.display_name
        }

        pending_id = await self.create_pending_entry(interaction, knowledge_data)

        if not pending_id:
            # 如果扣款了但提交失败，需要退款
            if self.purchase_info:
                from src.chat.features.odysseia_coin.service.coin_service import coin_service
                await coin_service.add_coins(
                    user_id=interaction.user.id,
                    amount=self.purchase_info.get('price', 0),
                    reason=f"知识纸条提交失败自动退款 (item_id: {self.purchase_info.get('item_id')})"
                )
                await interaction.followup.send("提交审核时发生错误，已自动退款，请稍后再试。", ephemeral=True)
            else:
                await interaction.response.send_message("提交审核时发生错误，请稍后再试。", ephemeral=True)
            return

        # 根据是否有购买信息，选择不同的响应方式
        response_method = interaction.followup.send if self.purchase_info else interaction.response.send_message
        await response_method(
            f"✅ 您的知识贡献 **{title}** 已成功提交审核！\n请关注频道内的公开投票。",
            ephemeral=True
        )

        review_settings = chat_config.WORLD_BOOK_CONFIG['review_settings']
        duration = review_settings['review_duration_minutes']
        approval_threshold = review_settings['approval_threshold']
        instant_approval_threshold = review_settings['instant_approval_threshold']
        rejection_threshold = review_settings['rejection_threshold']

        embed = discord.Embed(
            title="我收到了一张小纸条！",
            description=(
                f"**{interaction.user.display_name}** 递给我一张纸条，上面写着关于 **{title}** 的知识，大家觉得内容怎么样？\n\n"
                f"*审核将在{duration}分钟后自动结束。*"
            ),
            color=discord.Color.orange()
        )
        embed.add_field(name="类别", value=category, inline=True)
        embed.add_field(name="标题", value=title, inline=False)
        embed.add_field(name="内容预览", value=content[:500] + ('...' if len(content) > 500 else ''), inline=False)

        duration = REVIEW_SETTINGS['review_duration_minutes']
        approval_threshold = REVIEW_SETTINGS['approval_threshold']
        instant_approval_threshold = REVIEW_SETTINGS['instant_approval_threshold']
        rejection_threshold = REVIEW_SETTINGS['rejection_threshold']

        rules_text = (
            f"投票规则: {VOTE_EMOJI} 达到{approval_threshold}个通过 | "
            f"{VOTE_EMOJI} {duration}分钟内达到{instant_approval_threshold}个立即通过 | "
            f"{REJECT_EMOJI} 达到{rejection_threshold}个否决"
        )
        footer_text = f"提交者: {interaction.user.display_name} (ID: {interaction.user.id}) | 审核ID: {pending_id} | {rules_text}"
        embed.set_footer(text=footer_text)
        embed.timestamp = interaction.created_at

        review_message = await interaction.followup.send(embed=embed, wait=True)

        await self.update_message_id_for_pending_entry(pending_id, review_message.id)

        # 如果是通过商店购买，更新商店视图的余额
        if self.purchase_info:
            from src.chat.features.odysseia_coin.service.coin_service import coin_service
            new_balance = await coin_service.get_balance(interaction.user.id)
            # 注意：这里无法直接更新原始的商店 view 对象，这是一个待优化的点。
            # 简单的做法是提示用户手动刷新。
            await interaction.followup.send("你的知识已提交审核，商店余额已更新。你可能需要重新打开商店或点击刷新按钮查看最新余额。", ephemeral=True)

    async def developer_direct_add(self, interaction: discord.Interaction, category_name: str, title: str, content_text: str):
        """开发者直接添加知识条目，无需审核"""
        responder = interaction.followup.send if interaction.response.is_done() else interaction.response.send_message

        conn = self._get_world_book_connection()
        if not conn:
            await responder("❌ 数据库连接失败。", ephemeral=True)
            return

        try:
            cursor = conn.cursor()

            # 查找或创建类别
            cursor.execute("SELECT id FROM categories WHERE name = ?", (category_name,))
            category_row = cursor.fetchone()
            if category_row:
                category_id = category_row[0]
            else:
                cursor.execute("INSERT INTO categories (name) VALUES (?)", (category_name,))
                category_id = cursor.lastrowid
                log.info(f"开发者 {interaction.user.id} 创建了新类别: {category_name}")

            # 准备数据并插入
            content_dict = {"description": content_text}
            content_json = json.dumps(content_dict, ensure_ascii=False)
            clean_title = re.sub(r'[^\w\u4e00-\u9fff]', '_', title)[:50]
            import time
            entry_id = f"{clean_title}_{int(time.time())}"

            cursor.execute("""
                INSERT INTO general_knowledge (id, title, name, content_json, category_id, contributor_id, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """, (entry_id, title, title, content_json, category_id, interaction.user.id, 'approved'))
            
            conn.commit()
            log.info(f"开发者 {interaction.user.id} 已直接添加知识条目 '{title}' (ID: {entry_id})")

            # 异步触发RAG更新
            asyncio.create_task(incremental_rag_service.process_general_knowledge(entry_id))

            await responder(f"✅ **开发者后门**: 知识条目 **{title}** 已成功添加，无需审核。", ephemeral=True)

        except Exception as e:
            log.error(f"开发者直接添加知识条目时出错: {e}", exc_info=True)
            conn.rollback()
            await responder(f"❌ 添加时发生内部错误: {e}", ephemeral=True)
        finally:
            conn.close()
        