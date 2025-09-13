import discord
import logging
import json
import sqlite3
import os
import asyncio
from typing import Dict, Any

from src import config
from src.chat.features.world_book.services.incremental_rag_service import incremental_rag_service

log = logging.getLogger(__name__)

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
        
        # Discord ID输入框（可选）
        self.discord_id_input = discord.ui.TextInput(
            label="Discord ID（可选）",
            placeholder="请输入成员的Discord数字ID（如1234567890）",
            max_length=20,
            required=False
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
    
    async def save_community_member(self, interaction: discord.Interaction, member_data: Dict[str, str]) -> str | None:
        """保存社区成员档案到数据库"""
        conn = self._get_world_book_connection()
        if not conn:
            log.error("无法连接到世界书数据库，无法保存社区成员档案")
            return False
            
        try:
            cursor = conn.cursor()
            
            # 构建成员数据
            content_data = {
                "name": member_data.get('name', '未提供'),
                "personality": member_data.get('personality', '未提供'),
                "background": member_data.get('background', '未提供'),
                "preferences": member_data.get('preferences', '未提供'),
                "uploaded_by": interaction.user.id,
                "uploaded_by_name": interaction.user.display_name
            }
            
            # 将数据转换为JSON格式
            content_json = json.dumps(content_data, ensure_ascii=False)
            
            # 生成唯一的成员ID
            import time
            import re
            clean_name = re.sub(r'[^\w\u4e00-\u9fff]', '_', member_data['name'])[:50]
            member_id = f"community_{clean_name}_{int(time.time())}"
            
            # 插入新成员记录（不绑定到特定用户）
            cursor.execute(
                "INSERT INTO community_members (id, title, discord_number_id, content_json) VALUES (?, ?, ?, ?)",
                (member_id, f"社区成员档案 - {member_data['name']}", member_data.get('discord_id'), content_json)
            )
            
            conn.commit()
            log.info(f"已成功保存社区成员档案: {member_id} ({member_data['name']})")
            return member_id
            
        except sqlite3.Error as e:
            log.error(f"保存社区成员档案时发生数据库错误: {e}", exc_info=True)
            conn.rollback()
            return None
        except Exception as e:
            log.error(f"保存社区成员档案时发生未知错误: {e}", exc_info=True)
            conn.rollback()
            return None
        finally:
            conn.close()
    
    async def on_submit(self, interaction: discord.Interaction):
        """当用户提交模态窗口时调用"""
        # 获取用户输入的值
        member_name = self.member_name_input.value.strip()
        discord_id = self.discord_id_input.value.strip()
        personality = self.personality_input.value.strip()
        background = self.background_input.value.strip()
        preferences = self.preferences_input.value.strip()
        
        # 基本验证
        if not member_name:
            await interaction.response.send_message("成员名称不能为空。", ephemeral=True)
            return
            
        if not personality:
            await interaction.response.send_message("性格特点不能为空。", ephemeral=True)
            return
        
        # 构建成员数据
        member_data = {
            'name': member_name,
            'discord_id': discord_id if discord_id else None,
            'personality': personality,
            'background': background if background else '未提供',
            'preferences': preferences if preferences else '未提供'
        }
        
        # 保存到数据库并获取 member_id
        member_id = await self.save_community_member(interaction, member_data)
        
        if member_id:
            # 异步调用增量RAG处理（不阻塞用户响应）
            asyncio.create_task(incremental_rag_service.process_community_member(member_id))
            
            # 发送成功消息给用户
            await interaction.response.send_message(
                f"感谢您的贡献！社区成员档案已成功上传。\n\n"
                f"**成员名称**: {member_name}\n"
                f"**性格特点**: {personality[:100]}{'...' if len(personality) > 100 else ''}",
                ephemeral=True
            )
            
            # 构建并发送公共广播消息
            embed = discord.Embed(
                title="✨ 新的社区成员档案上传！",
                description=f"**{interaction.user.display_name}** 上传了一个新的社区成员档案！",
                color=discord.Color.green()
            )
            embed.add_field(name="成员名称", value=member_name, inline=True)
            if discord_id:
                embed.add_field(name="Discord ID", value=discord_id, inline=True)
            embed.add_field(name="性格特点", value=personality[:300] + ('...' if len(personality) > 300 else ''), inline=False)
            if background:
                embed.add_field(name="背景信息", value=background[:200] + ('...' if len(background) > 200 else ''), inline=False)
            if preferences:
                embed.add_field(name="喜好偏好", value=preferences[:200] + ('...' if len(preferences) > 200 else ''), inline=False)
            embed.set_footer(text=f"上传者: {interaction.user.display_name} (ID: {interaction.user.id})")
            embed.timestamp = interaction.created_at
            
            # 在当前频道发送广播
            await interaction.channel.send(embed=embed)
            
        else:
            await interaction.response.send_message(
                "很抱歉，上传社区成员档案时出现了问题。请稍后再试。",
                ephemeral=True
            )