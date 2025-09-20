import discord
import logging
import json
import sqlite3
import os
import asyncio
from typing import Dict, Any
from datetime import datetime, timedelta

from src import config
from src.chat.config import chat_config
# 移除 incremental_rag_service 的导入，因为我们不再直接处理
# from src.chat.features.world_book.services.incremental_rag_service import incremental_rag_service

log = logging.getLogger(__name__)

# 获取审核配置
REVIEW_SETTINGS = chat_config.WORLD_BOOK_CONFIG['review_settings']
VOTE_EMOJI = REVIEW_SETTINGS['vote_emoji']
REJECT_EMOJI = REVIEW_SETTINGS['reject_emoji']

class CommunityMemberUploadModal(discord.ui.Modal, title="上传社区成员档案"):
    """用于用户上传社区成员档案的模态窗口"""
    
    def __init__(self):
        super().__init__()
        
        # 成员名称输入框
        self.member_name_input = discord.ui.TextInput(
            label="成员名称",
            placeholder="请输入社区成员的名称或昵称",
            max_length=100,
            required=True
        )
        self.add_item(self.member_name_input)
        
        # Discord ID输入框
        self.discord_id_input = discord.ui.TextInput(
            label="Discord ID",
            placeholder="请输入成员的Discord数字ID（必填）",
            max_length=20,
            required=True
        )
        self.add_item(self.discord_id_input)
        
        # 性格特点输入框
        self.personality_input = discord.ui.TextInput(
            label="性格特点",
            placeholder="描述该成员的性格特点、行为方式等",
            style=discord.TextStyle.paragraph,
            max_length=500,
            required=True
        )
        self.add_item(self.personality_input)
        
        # 背景信息输入框
        self.background_input = discord.ui.TextInput(
            label="背景信息",
            placeholder="描述该成员的背景故事、经历等",
            style=discord.TextStyle.paragraph,
            max_length=1000,
            required=False
        )
        self.add_item(self.background_input)
        
        # 喜好偏好输入框
        self.preferences_input = discord.ui.TextInput(
            label="喜好偏好",
            placeholder="描述该成员的喜好、兴趣、习惯等",
            style=discord.TextStyle.paragraph,
            max_length=500,
            required=False
        )
        self.add_item(self.preferences_input)
    
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
    
    async def create_pending_entry(self, interaction: discord.Interaction, member_data: Dict[str, Any]) -> int | None:
        """将提交的数据作为待审核条目存入数据库"""
        conn = self._get_world_book_connection()
        if not conn:
            return None
            
        try:
            cursor = conn.cursor()
            
            # 从配置中获取审核时长
            duration_minutes = chat_config.WORLD_BOOK_CONFIG['review_settings']['review_duration_minutes']
            expires_at = datetime.utcnow() + timedelta(minutes=duration_minutes)
            
            # 将原始提交数据序列化为 JSON
            data_json = json.dumps(member_data, ensure_ascii=False)
            
            cursor.execute("""
                INSERT INTO pending_entries
                (entry_type, data_json, channel_id, guild_id, proposer_id, expires_at, message_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                'community_member',
                data_json,
                interaction.channel_id,
                interaction.guild_id,
                interaction.user.id,
                expires_at.isoformat(),
                -1 # 临时 message_id
            ))
            
            pending_id = cursor.lastrowid
            conn.commit()
            log.info(f"已创建待审核条目 #{pending_id} (类型: community_member)，提交者: {interaction.user.id}")
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
        member_name = self.member_name_input.value.strip()
        discord_id = self.discord_id_input.value.strip()
        personality = self.personality_input.value.strip()
        background = self.background_input.value.strip()
        preferences = self.preferences_input.value.strip()
        
        # --- 新增：校验 Discord ID 是否为纯数字 ---
        if discord_id and not discord_id.isdigit():
            await interaction.response.send_message(
                "❌ Discord ID 必须为纯数字，请重新提交。",
                ephemeral=True
            )
            return
        
        if not member_name or not personality:
            await interaction.response.send_message("成员名称和性格特点不能为空。", ephemeral=True)
            return
        
        member_data = {
            'name': member_name,
            'discord_id': discord_id if discord_id else None,
            'personality': personality,
            'background': background if background else '未提供',
            'preferences': preferences if preferences else '未提供',
            'uploaded_by': interaction.user.id,
            'uploaded_by_name': interaction.user.display_name
        }

        # --- 新增逻辑：检查是创建还是更新 ---
        conn = self._get_world_book_connection()
        existing_entry_id = None
        if conn and discord_id:
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id FROM community_members WHERE discord_number_id = ? AND status = 'approved'",
                    (discord_id,)
                )
                row = cursor.fetchone()
                if row:
                    existing_entry_id = row['id']
                    member_data['update_target_id'] = existing_entry_id
                    log.info(f"检测到针对现有社区成员 (Discord ID: {discord_id}, Entry ID: {existing_entry_id}) 的更新请求。")
            except sqlite3.Error as e:
                log.error(f"查询现有社区成员时出错: {e}", exc_info=True)
            finally:
                conn.close()
        # --- 新增逻辑结束 ---
        
        # 1. 将数据存入 pending_entries 表
        pending_id = await self.create_pending_entry(interaction, member_data)
        
        if not pending_id:
            await interaction.response.send_message("提交审核时发生错误，请稍后再试。", ephemeral=True)
            return

        # 2. 发送一个临时的确认消息
        await interaction.response.send_message(
            f"✅ 您的社区成员档案 **{member_name}** 已成功提交审核！\n请关注频道内的公开投票。",
            ephemeral=True
        )

        # 3. 构建并发送公开的审核 Embed
        review_settings = chat_config.WORLD_BOOK_CONFIG['review_settings']
        duration = review_settings['review_duration_minutes']
        approval_threshold = review_settings['approval_threshold']
        instant_approval_threshold = review_settings['instant_approval_threshold']
        rejection_threshold = review_settings['rejection_threshold']

        embed_title = "新的社区成员档案"
        embed_description = f"**{interaction.user.display_name}** 提交了一份新的社区成员档案，需要社区进行审核。"
        if existing_entry_id:
            embed_title = "社区成员档案更新"
            embed_description = f"**{interaction.user.display_name}** 提交了一份针对现有成员的档案更新，需要社区进行审核。"

        embed = discord.Embed(
            title=embed_title,
            description=(
                f"{embed_description}\n\n"
                f"*审核将在{duration}分钟后自动结束。*"
            ),
            color=discord.Color.blue() if existing_entry_id else discord.Color.orange()
        )
        embed.add_field(name="成员名称", value=member_name, inline=True)
        if discord_id:
            embed.add_field(name="Discord ID", value=discord_id, inline=True)
        embed.add_field(name="性格特点", value=personality[:300] + ('...' if len(personality) > 300 else ''), inline=False)
        if background:
            embed.add_field(name="背景信息", value=background[:200] + ('...' if len(background) > 200 else ''), inline=False)
        if preferences:
            embed.add_field(name="喜好偏好", value=preferences[:200] + ('...' if len(preferences) > 200 else ''), inline=False)
        
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
        
        # 4. 发送消息并添加投票按钮
        # 使用 followup 发送，因为 response 已经被用于临时消息
        review_message = await interaction.followup.send(embed=embed, wait=True)
        
        # 5. 更新数据库中的 message_id
        await self.update_message_id_for_pending_entry(pending_id, review_message.id)
        
        # 6. 添加投票表情