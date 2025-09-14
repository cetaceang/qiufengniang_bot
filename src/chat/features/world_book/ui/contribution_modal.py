import discord
import logging
import json
import sqlite3
import os
from typing import Dict, Any
from datetime import datetime, timedelta

from src import config
from src.chat.config import chat_config

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
    "俚语"
]

class WorldBookContributionModal(discord.ui.Modal, title="贡献知识"):
    """用于用户提交世界书知识条目的模态窗口"""
    
    def __init__(self):
        super().__init__()
        
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
        category = self.category_input.value.strip()
        title = self.title_input.value.strip()
        content = self.content_input.value.strip()
        
        if category not in AVAILABLE_CATEGORIES:
            await interaction.response.send_message(f"无效的类别。请从以下选项中选择: {', '.join(AVAILABLE_CATEGORIES)}", ephemeral=True)
            return
            
        if not all([category, title, content]):
            await interaction.response.send_message("类别、标题和内容均不能为空。", ephemeral=True)
            return
            
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
            await interaction.response.send_message("提交审核时发生错误，请稍后再试。", ephemeral=True)
            return

        await interaction.response.send_message(
            f"✅ 您的知识贡献 **{title}** 已成功提交审核！\n请关注频道内的公开投票。",
            ephemeral=True
        )

        review_settings = chat_config.WORLD_BOOK_CONFIG['review_settings']
        duration = review_settings['review_duration_minutes']
        approval_threshold = review_settings['approval_threshold']
        instant_approval_threshold = review_settings['instant_approval_threshold']
        rejection_threshold = review_settings['rejection_threshold']

        embed = discord.Embed(
            title="新的世界之书贡献",
            description=(
                f"**{interaction.user.display_name}** 提交了一份新的知识条目，需要社区进行审核。\n\n"
                f"*审核将在{duration}分钟后自动结束。*"
            ),
            color=discord.Color.orange()
        )
        embed.add_field(name="类别", value=category, inline=True)
        embed.add_field(name="标题", value=title, inline=False)
        embed.add_field(name="内容预览", value=content[:500] + ('...' if len(content) > 500 else ''), inline=False)
        
        # 在 footer 中添加投票规则，使其不那么显眼
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
        