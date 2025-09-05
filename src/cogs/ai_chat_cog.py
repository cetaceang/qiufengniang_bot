# -*- coding: utf-8 -*-

import discord
from discord import app_commands
from discord.ext import commands
import logging
import re
from typing import Optional, List
import aiohttp

# 导入AI服务
from ..services.gemini_service import gemini_service
# 导入上下文服务
from ..services.context_service import context_service
# 导入世界书服务
from ..world_book.services.world_book_service import world_book_service
# 导入好感度服务
from ..affection.service.affection_service import affection_service
# 导入数据库管理器
from ..utils.database import db_manager
# 导入类脑币服务
from ..odysseia_coin.service.coin_service import coin_service
from ..services.regex_service import regex_service
 
log = logging.getLogger(__name__)

class AIChatCog(commands.Cog):
    """处理AI聊天功能的Cog，包括@mention回复"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        context_service.set_bot_instance(bot) # 将bot实例传递给context_service
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """
        监听所有消息，当bot被@mention时进行回复
        """
        # 忽略机器人自己的消息
        if message.author.bot:
            return

        # 检查用户是否被拉黑
        guild_id = message.guild.id if message.guild else 0
        if await db_manager.is_user_blacklisted(message.author.id, guild_id):
            # 如果用户被拉黑，则不处理消息
            return
         
        # 检查消息是否@mention了当前bot
        if self.bot.user in message.mentions:
            await self.handle_mention(message)
    
    async def handle_mention(self, message: discord.Message):
        """
        处理@mention消息，生成AI回复
        """
        image_data_list = []
        try:
            # --- 冷却检查 ---
            # 在显示“正在输入”之前，先检查用户是否处于冷却状态
            cooldown_type = await coin_service.get_user_cooldown_type(message.author.id)
            if await gemini_service.is_user_on_cooldown(message.author.id, cooldown_type):
                log.info(f"用户 {message.author.id} 处于冷却状态，已提前跳过处理。")
                return # 静默返回，不显示“正在输入”
            
            # 显示"正在输入"状态
            async with message.channel.typing():
                # 提取纯文本内容（移除@mention部分）
                clean_content = self._clean_message_content(message.content, message.mentions)

                # 处理图片附件（直接使用CDN URL）
                if message.attachments:
                    for attachment in message.attachments:
                        if attachment.content_type and attachment.content_type.startswith('image/'):
                            try:
                                # 异步读取图片数据为字节
                                image_bytes = await attachment.read()
                                # 添加额外的检查以确保数据有效
                                if image_bytes and isinstance(image_bytes, bytes):
                                    image_data_list.append({
                                        'mime_type': attachment.content_type,
                                        'data': image_bytes  # 使用 data 键传递字节数据
                                    })
                                    log.debug(f"成功读取图片附件: {attachment.filename}, MIME类型: {attachment.content_type}, 大小: {len(image_bytes)} 字节")
                                else:
                                    log.warning(f"图片附件 {attachment.filename} 读取失败: 数据无效或不是字节类型")
                            except Exception as e:
                                log.error(f"读取图片附件 {attachment.filename} 时出错: {e}")
                
                # --- 新增：处理回复消息 ---
                replied_message_content = ""
                if message.reference and message.reference.message_id:
                    try:
                        # 尝试从缓存或API获取被回复的消息
                        ref_msg = await message.channel.fetch_message(message.reference.message_id)
                        if ref_msg and ref_msg.author:
                            # 清理被回复消息的内容
                            ref_content_cleaned = self._clean_message_content(ref_msg.content, ref_msg.mentions)
                            replied_message_content = f'[回复 @{ref_msg.author.display_name}: "{ref_content_cleaned}"] '
                            # --- 新增：处理被回复消息中的图片 ---
                            if ref_msg.attachments:
                                for attachment in ref_msg.attachments:
                                    if attachment.content_type and attachment.content_type.startswith('image/'):
                                        try:
                                            image_bytes = await attachment.read()
                                            if image_bytes:
                                                image_data_list.append({
                                                    'mime_type': attachment.content_type,
                                                    'data': image_bytes
                                                })
                                                log.debug(f"成功读取被回复消息中的图片: {attachment.filename}")
                                        except Exception as e:
                                            log.error(f"读取被回复消息的图片 {attachment.filename} 时出错: {e}")

                    except (discord.NotFound, discord.Forbidden):
                        log.warning(f"无法找到或无权访问被回复的消息 ID: {message.reference.message_id}")
                        pass # 获取失败则静默忽略
                
                # 将回复内容与当前消息内容合并
                final_content = f"{replied_message_content}{clean_content}"

                # 获取格式化后的频道上下文，并排除当前正在处理的这条消息
                channel_context = await context_service.get_formatted_channel_history(
                    message.channel.id,
                    message.author.id,
                    message.guild.id if message.guild else 0,
                    exclude_message_id=message.id
                )

                # --- 新增：世界书上下文检索 ---
                # --- 新增：将用户名和消息内容合并，用于世界书检索 ---
                # 这样可以允许世界书条目通过用户名来触发
                content_for_world_book = f"用户名: {message.author.display_name}\n{final_content}"
                world_book_entries = world_book_service.find_entries(channel_context, user_message=content_for_world_book)

                # 生成AI回复
                ai_response = await gemini_service.generate_response(
                    message.author.id,
                    message.guild.id if message.guild else 0,
                    final_content if final_content.strip() else None, # 如果没有文本，传递None
                    images=image_data_list if image_data_list else None, # 如果没有图片，传递None
                    user_name=message.author.display_name, # 传递用户昵称/名称
                    channel_context=channel_context,
                    world_book_entries=world_book_entries, # 传递世界书条目
                    cooldown_type=cooldown_type # 复用之前检查过的冷却类型
                )

                if not ai_response:
                    log.info(f"用户 {message.author.id} 处于冷却状态，已跳过回复。")
                    return

                log.info(f"原始AI回复: {ai_response}")
                
                # 在发送前，清理AI回复中可能包含的自身名字前缀
                bot_name_prefix = "类脑娘:"
                if ai_response.startswith(bot_name_prefix):
                    ai_response = ai_response[len(bot_name_prefix):].lstrip()

                # 将多段回复的双换行符替换为单换行符
                final_response = ai_response.replace('\n\n', '\n')
                
                # 回复消息，不@用户
                await message.reply(final_response, mention_author=False)

            # --- 后续处理（移出 typing 块以尽快结束“正在输入”状态） ---
            
            # --- 好感度系统集成 ---
            # 在成功回复后，尝试增加好感度
            try:
                guild_id = message.guild.id if message.guild else 0
                await affection_service.increase_affection_on_message(message.author.id, guild_id)
            except Exception as aff_e:
                log.error(f"增加用户 {message.author.id} 的好感度时出错: {aff_e}")
            # --- 好感度系统集成结束 ---

            # --- 每日首次对话奖励 ---
            try:
                reward_granted = await coin_service.grant_daily_message_reward(message.author.id)
                if reward_granted:
                    log.info(f"已为用户 {message.author.id} 发放每日首次对话奖励。")
            except Exception as coin_e:
                log.error(f"为用户 {message.author.id} 发放每日对话奖励时出错: {coin_e}")
            # --- 每日首次对话奖励结束 ---

            log.info(f"已为用户 {message.author} 生成AI回复")

        except Exception as e:
            log.error(f"[AIChatCog] 处理@mention消息时出错: {e}", exc_info=True)
            try:
                await message.reply("抱歉，处理你的消息时出现了问题，请稍后再试。", mention_author=False)
            except:
                pass
    
    def _clean_message_content(self, content: str, mentions: list) -> str:
        """
        清理消息内容，移除@mention部分，并清理括号内容。
        """
        # 移除所有@mention
        for user in mentions:
            content = content.replace(f'<@{user.id}>', '').replace(f'<@!{user.id}>', '')
        
        # 使用新的清理函数，清理用户输入中的所有指定括号
        content = regex_service.clean_user_input(content)
        
        # 移除多余空格和换行
        content = content.strip()
        
        return content

    @app_commands.command(name="clear_context", description="清除指定用户的AI对话上下文")
    @app_commands.describe(user="选择要清除上下文的用户")
    @app_commands.default_permissions(administrator=True)
    async def clear_context(self, interaction: discord.Interaction, user: discord.User):
        """斜杠命令，用于清除用户的AI对话历史"""
        try:
            guild_id = interaction.guild.id if interaction.guild else 0
            # 调用 context_service 清除用户上下文
            await context_service.clear_user_context(user.id, guild_id)
            await interaction.response.send_message(f"已成功清除用户 {user.mention} 的对话上下文。", ephemeral=True)
            log.info(f"管理员 {interaction.user} 清除了用户 {user.id} 的对话上下文")
        except Exception as e:
            log.error(f"清除用户上下文时出错: {e}")
            await interaction.response.send_message("清除上下文时发生错误，请检查日志。", ephemeral=True)

    @app_commands.command(name="刷新记忆", description="(管理员) 将当前位置设为频道记忆的最新起点。")
    @app_commands.default_permissions(administrator=True)
    async def refresh_channel_memory(self, interaction: discord.Interaction):
        """
        斜杠命令，用于将当前命令的位置设置为频道记忆的新锚点。
        执行后，AI将只参考此命令之后发生的消息。
        """
        try:
            guild_id = interaction.guild.id if interaction.guild else 0
            channel_id = interaction.channel.id
            channel_name = interaction.channel.name
            
            # 获取此命令之前的最后一条消息
            last_message = [msg async for msg in interaction.channel.history(limit=1)]
            
            if not last_message:
                # 如果频道中没有消息，则不设置锚点，并告知用户
                await interaction.response.send_message(
                    f"频道 `#{channel_name}` 中还没有任何消息，无法设置记忆起点。",
                    ephemeral=True
                )
                log.warning(f"管理员 {interaction.user} 尝试在空频道 #{channel_name} 中刷新记忆，但失败了。")
                return

            anchor_message_id = last_message[0].id

            # 调用数据库管理器来设置或更新锚点
            await db_manager.set_channel_memory_anchor(guild_id, channel_id, anchor_message_id)

            await interaction.response.send_message(
                f"好的，我已经刷新了对 `#{channel_name}` 频道的记忆。\n"
                f"从现在开始，我将只参考消息 ID `{anchor_message_id}` 之后的新对话作为上下文。",
                ephemeral=True
            )
            log.info(f"管理员 {interaction.user} 在频道 #{channel_name} 设置了新的记忆锚点: {anchor_message_id}。")
        except Exception as e:
            log.error(f"处理 refresh_channel_memory 命令时出错: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("执行此命令时发生未知错误，请检查日志。", ephemeral=True)

    @app_commands.command(name="清除频道记忆", description="(管理员) 清除当前频道的记忆锚点，解决上下文卡住的问题。")
    @app_commands.default_permissions(administrator=True)
    async def clear_channel_memory(self, interaction: discord.Interaction):
        """
        斜杠命令，用于删除当前频道的记忆锚点。
        """
        try:
            guild_id = interaction.guild.id if interaction.guild else 0
            channel_id = interaction.channel.id
            channel_name = interaction.channel.name

            deleted_rows = await db_manager.delete_channel_memory_anchor(guild_id, channel_id)

            if deleted_rows > 0:
                await interaction.response.send_message(
                    f"已成功清除 `#{channel_name}` 频道的记忆锚点。\n"
                    "AI现在会参考此前的完整历史记录。",
                    ephemeral=True
                )
                log.info(f"管理员 {interaction.user} 清除了频道 #{channel_name} 的记忆锚点。")
            else:
                await interaction.response.send_message(
                    f"`#{channel_name}` 频道没有设置记忆锚点，无需清除。",
                    ephemeral=True
                )
        except Exception as e:
            log.error(f"处理 clear_channel_memory 命令时出错: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("执行此命令时发生未知错误，请检查日志。", ephemeral=True)
    
async def setup(bot: commands.Bot):
    """将这个Cog添加到机器人中"""
    await bot.add_cog(AIChatCog(bot))