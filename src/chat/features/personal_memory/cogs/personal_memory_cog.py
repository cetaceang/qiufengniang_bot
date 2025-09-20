import discord
from discord.ext import commands, tasks
import logging
import re
from typing import Dict
from datetime import datetime, timedelta, timezone

from src.chat.config.chat_config import PERSONAL_MEMORY_CONFIG
from ..services.personal_memory_service import personal_memory_service
from ..ui.profile_modal import PROFILE_MODAL_CUSTOM_ID

log = logging.getLogger(__name__)

class PersonalMemoryCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.service = personal_memory_service
        # 直接引用 service 中定义的追踪字典，以确保状态统一管理
        self.approval_message_ids = self.service.approval_message_ids
        # 启动后台清理任务
        self.cleanup_expired_approvals.start()

    def cog_unload(self):
        """Cog卸载时停止后台任务。"""
        self.cleanup_expired_approvals.cancel()

    @commands.Cog.listener('on_interaction')
    async def on_modal_submit(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.modal_submit:
            return
        
        custom_id = interaction.data.get("custom_id")
        if custom_id != PROFILE_MODAL_CUSTOM_ID:
            return

        await interaction.response.defer(ephemeral=True)

        try:
            # 从 interaction.data 中安全地提取数据
            components = interaction.data.get('components', [])
            
            # 创建一个字典来更容易地通过 custom_id 查找 value
            # 注意：这里的 custom_id 是我们在 Modal 中定义的字段名
            values_by_id = {
                comp['components'][0]['custom_id']: comp['components'][0]['value']
                for comp in components if comp.get('components')
            }

            # 现在根据字段名来构建 profile_data
            profile_data = {
                'name': values_by_id.get('name', ''),
                'personality': values_by_id.get('personality', ''),
                'background': values_by_id.get('background', ''),
                'preferences': values_by_id.get('preferences', '')
            }
            
            await self.service.save_user_profile(interaction.user.id, profile_data)
            
            embed = discord.Embed(
                title="个人档案已保存",
                description="你的个人档案已成功保存！类脑娘现在对你有了更深的了解。",
                color=discord.Color.green()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            log.info(f"用户 {interaction.user.id} 通过模态框成功保存了个人档案。")

        except Exception as e:
            log.error(f"处理用户 {interaction.user.id} 的个人档案提交时出错: {e}", exc_info=True)
            await interaction.followup.send("保存你的档案时发生了错误，请稍后再试。", ephemeral=True)


    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        # 核心优化：只处理被追踪的投票消息
        if payload.message_id not in self.approval_message_ids:
            return

        if payload.user_id == self.bot.user.id:
            return

        channel = self.bot.get_channel(payload.channel_id)
        if not isinstance(channel, discord.TextChannel):
            return

        try:
            message = await channel.fetch_message(payload.message_id)
        except discord.NotFound:
            log.warning(f"在 on_raw_reaction_add 中无法找到消息 {payload.message_id}，将从监听列表中移除。")
            self.approval_message_ids.pop(payload.message_id, None)
            return
        except discord.Forbidden:
            log.warning(f"无权访问消息 {payload.message_id}，将从监听列表中移除。")
            self.approval_message_ids.pop(payload.message_id, None)
            return


        if not message.author.id == self.bot.user.id or not message.embeds:
            return

        embed = message.embeds[0]
        if embed.title != "【社区投票】激活个人记忆功能" or not embed.footer.text.startswith("申请用户ID:"):
            return
        
        approval_emoji = PERSONAL_MEMORY_CONFIG["APPROVAL_EMOJI"]
        if str(payload.emoji) != approval_emoji:
            return

        for reaction in message.reactions:
            if str(reaction.emoji) == approval_emoji:
                current_votes = reaction.count - 1
                approval_threshold = PERSONAL_MEMORY_CONFIG["APPROVAL_THRESHOLD"]

                if current_votes >= approval_threshold:
                    # 修复竞争条件：一旦票数达标，立即从监听中移除，再处理。
                    # 这样可以防止多个并发的reaction事件重复触发process_approval。
                    if message.id in self.approval_message_ids:
                        self.approval_message_ids.pop(message.id, None)
                        log.info(f"投票 {message.id} 票数达标，已从监听列表移除，准备处理...")
                        await self.process_approval(message, embed)
                break

    async def process_approval(self, message: discord.Message, embed: discord.Embed):
        match = re.search(r"申请用户ID: (\d+)", embed.footer.text)
        if not match:
            return

        target_user_id = int(match.group(1))
        
        # 尝试从服务器获取成员对象，如果失败（例如用户已离开），则回退到获取用户对象
        target_user = message.guild.get_member(target_user_id)
        if not target_user:
            try:
                target_user = await self.bot.fetch_user(target_user_id)
            except discord.NotFound:
                log.warning(f"找不到ID为 {target_user_id} 的用户。")
                return

        # 检查功能是否已经解锁
        user_data = await self.service.db_manager.get_user_profile(target_user_id)
        if user_data and user_data['has_personal_memory']:
            log.info(f"用户 {target_user_id} 的个人记忆功能已经解锁，无需重复操作。")
            # 即使已解锁，也更新一下消息状态避免混淆
            if embed.title.startswith("【社区投票】"):
                 await message.edit(content="此用户的个人记忆功能已被激活。", embed=None, view=None)
                 await message.clear_reactions()
            # 清理操作已在 on_raw_reaction_add 中提前完成，此处无需重复操作
            return

        # 解锁功能并发送私信提示
        await self.service.unlock_personal_memory_for_user(target_user)

        # 更新原始消息，宣布结果
        new_embed = embed.copy()
        new_embed.title = "【投票通过】个人记忆功能已激活"
        new_embed.description = f"感谢社区的踊跃投票！功能已为 {target_user.mention} 成功激活。"
        new_embed.color = discord.Color.green()
        
        await message.edit(embed=new_embed, view=None) # 移除按钮
        await message.clear_reactions()
        log.info(f"用户 {target_user_id} 的个人记忆功能投票通过并已激活。")
        
        # 最终清理操作已在 on_raw_reaction_add 中提前完成，此处无需重复操作
        log.debug(f"消息 {message.id} 已处理完毕。")

    @tasks.loop(hours=1)
    async def cleanup_expired_approvals(self):
        """每小时运行一次，清理过期的投票消息。"""
        now = datetime.now(timezone.utc)
        expiration_delta = timedelta(hours=PERSONAL_MEMORY_CONFIG.get("APPROVAL_TIMEOUT_HOURS", 24))
        
        # 创建一个副本进行迭代，因为我们可能会在循环中修改原始字典
        expired_ids = [
            msg_id for msg_id, start_time in self.approval_message_ids.items()
            if now - start_time > expiration_delta
        ]

        if not expired_ids:
            return

        log.info(f"开始清理 {len(expired_ids)} 个过期的投票...")

        for message_id in expired_ids:
            # 从追踪字典中移除
            self.approval_message_ids.pop(message_id, None)
            log.info(f"投票 {message_id} 已过期，已从监听列表中移除。")

            # (可选) 尝试编辑消息，告知用户投票已过期
            # 注意：这需要机器人缓存了消息或者进行API调用，可能失败
            try:
                # 这是一个简化的示例，实际可能需要从 channel_id 获取 channel
                # 这里我们假设无法直接获取 channel 和 message，仅作日志记录
                pass # 在真实场景中，你可能需要存储 channel_id 来获取消息
            except Exception as e:
                log.warning(f"尝试编辑过期的投票消息 {message_id} 时出错: {e}")

    @cleanup_expired_approvals.before_loop
    async def before_cleanup(self):
        """在任务开始前，等待机器人准备就绪。"""
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(PersonalMemoryCog(bot))