import discord
from discord.ext import commands
import logging
import re
from typing import Dict

from src.chat.config.chat_config import PERSONAL_MEMORY_CONFIG
from ..services.personal_memory_service import personal_memory_service
from ..ui.profile_modal import PROFILE_MODAL_CUSTOM_ID

log = logging.getLogger(__name__)

class PersonalMemoryCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.service = personal_memory_service
        self.approval_message_ids = set()
        # 将 cog 实例传递给 service，以便 service 可以回调
        self.service.cog = self

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
        # --- 优化：前置检查 ---
        # 如果消息ID不在我们追踪的投票消息列表中，则直接忽略事件，避免API调用
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

        # --- 优化：处理完毕后从缓存中移除 ---
        self.approval_message_ids.discard(message.id)


async def setup(bot: commands.Bot):
    await bot.add_cog(PersonalMemoryCog(bot))