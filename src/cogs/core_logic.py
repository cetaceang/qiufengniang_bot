# -*- coding: utf-8 -*-

import logging
import discord
from discord.ext import commands
import json
from typing import List, Dict, Any

# 从我们自己的模块中导入
from ..utils.database import db_manager
from ..utils.helpers import create_embed_from_template
from .. import config

log = logging.getLogger(__name__)


# --- 新的交互式私信视图 (支持多选) ---

class TagSelect(discord.ui.Select):
    """让用户选择兴趣标签的下拉菜单。"""
    def __init__(self, bot: commands.Bot, guild_id: int, tags: List[Dict[str, Any]]):
        self.bot = bot
        self.guild_id = guild_id
        
        options = [
            discord.SelectOption(
                label=tag['tag_name'],
                value=str(tag['tag_id']),
                description=tag['description']
            ) for tag in tags
        ]
        if not options:
            options.append(discord.SelectOption(label="没有可用的引导方向", value="disabled", default=True))
        
        super().__init__(
            placeholder="请选择一个或多个你感兴趣的方向...",
            min_values=1,
            max_values=len(options) if options[0].value != "disabled" else 1,
            options=options,
            disabled=not tags
        )

    async def callback(self, interaction: discord.Interaction):
        # 禁用视图，防止重复提交
        for item in self.view.children:
            item.disabled = True
        await interaction.response.edit_message(view=self.view)

        selected_tag_ids = [int(v) for v in self.values]

        try:
            # --- 路径合并逻辑 ---
            merged_path = []
            seen_location_ids = set()
            all_tags_info = []

            for tag_id in selected_tag_ids:
                tag_info = db_manager.get_tag_by_id(tag_id)
                if tag_info:
                    all_tags_info.append(tag_info)
                
                path_steps = db_manager.get_path_for_tag(tag_id)
                for step in path_steps:
                    if step['location_id'] not in seen_location_ids:
                        merged_path.append(dict(step))
                        seen_location_ids.add(step['location_id'])
            
            if not merged_path:
                await interaction.followup.send("❌ 抱歉，您选择的方向下没有配置任何有效的引导路径。请联系管理员。", ephemeral=True)
                return

            # --- 寻找入口点 ---
            first_step_config = None
            for step in merged_path:
                channel_config = db_manager.get_channel_message(step['location_id'])
                if channel_config and channel_config.get('deployed_message_id'):
                    first_step_config = channel_config
                    break
            
            if not first_step_config:
                await interaction.followup.send("❌ 抱歉，该引导路径的入口点尚未部署。请联系管理员。", ephemeral=True)
                return

            # --- [新] 发送包含路径预览的最终消息 ---
            guild = self.bot.get_guild(self.guild_id)
            if not guild:
                log.error(f"在TagSelect回调中无法找到服务器: {self.guild_id}")
                await interaction.followup.send("❌ 发生内部错误，无法识别您所在的服务器。", ephemeral=True)
                return

            # 1. 生成路径预览字符串
            path_preview_string = " -> ".join([f"<#{step['location_id']}>" for step in merged_path])

            # 2. 获取模板并构建基础 Embed
            selected_tag_names = [t['tag_name'] for t in all_tags_info]
            template = db_manager.get_message_template(self.guild_id, "prompt_message")
            embed = create_embed_from_template(
                template,
                guild,
                user=interaction.user,
                tag_name=", ".join(selected_tag_names)
            )

            # 3. 将路径预览添加到 Embed 描述中
            original_description = embed.description or ""
            embed.description = (
                f"{original_description}\n\n"
                f"**根据你的选择，我为你规划了以下浏览路径：**\n"
                f"{path_preview_string}\n\n"
                f"点击下方按钮，开始你的旅程吧！"
            )

            # 4. 创建包含“出发”按钮的 View
            first_channel_id = merged_path[0]['location_id']
            first_channel = guild.get_channel_or_thread(first_channel_id)
            
            # 极端情况处理：如果第一个地点都找不到了
            if not first_channel:
                await interaction.followup.send("❌ 路径的起始地点似乎已失效，请联系管理员。", ephemeral=True)
                return

            # --- 新逻辑：优先跳转到永久消息 ---
            first_step_config = db_manager.get_channel_message(first_channel_id)
            deployed_message_id = first_step_config.get('deployed_message_id') if first_step_config else None

            if deployed_message_id:
                jump_url = f"https://discord.com/channels/{guild.id}/{first_channel_id}/{deployed_message_id}"
            else:
                jump_url = first_channel.jump_url # 备用方案

            final_view = discord.ui.View()
            final_view.add_item(discord.ui.Button(
                label=f"出发！前往第一站：{first_channel.name}",
                style=discord.ButtonStyle.link,
                url=jump_url,
                emoji="🚀"
            ))

            # 5. 编辑原始消息，显示新的预览面板
            await interaction.edit_original_response(embed=embed, view=final_view)

            # --- 更新数据库 ---
            db_manager.update_user_progress(
                interaction.user.id,
                self.guild_id,
                status=config.USER_STATUS_IN_PROGRESS,
                selected_tags_json=json.dumps(selected_tag_ids),
                generated_path_json=json.dumps(merged_path)
            )
            log.info(f"用户 {interaction.user.name} 选择了标签 {selected_tag_names} 并生成了合并路径。")

        except Exception as e:
            log.error(f"处理标签选择回调时出错: {e}", exc_info=True)
            await interaction.followup.send("处理您的选择时发生了一个未知的错误，请稍后再试。", ephemeral=True)


class InitialGuidanceView(discord.ui.View):
    """引导流程开始时发送给用户的私信视图，包含标签选择。"""
    def __init__(self, bot: commands.Bot, guild_id: int, tags: List[Dict[str, Any]], timeout: float = 300.0):
        super().__init__(timeout=timeout)
        self.add_item(TagSelect(bot, guild_id, tags))


class CoreLogic(commands.Cog):
    """处理机器人核心后台逻辑。"""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.roles == after.roles:
            return

        trigger_roles_data = db_manager.get_trigger_roles(after.guild.id)
        if not trigger_roles_data:
            return
        
        trigger_role_ids = {role['role_id'] for role in trigger_roles_data}
        roles_before = {role.id for role in before.roles}
        roles_after = {role.id for role in after.roles}
        gained_roles = roles_after - roles_before
        
        if not any(role_id in trigger_role_ids for role_id in gained_roles):
            return

        # # [测试时禁用] 检查用户是否已在引导中
        # user_progress = db_manager.get_user_progress(after.id, after.guild.id)
        # if user_progress and user_progress['status'] in [config.USER_STATUS_IN_PROGRESS, config.USER_STATUS_COMPLETED]:
        #     log.info(f"用户 {after.name} 已有引导进度，跳过重复触发。")
        #     return

        log.info(f"检测到用户 {after.name} 获得触发身份组，准备触发引导流程。")
        await self.start_guidance_flow(after)

    async def start_guidance_flow(self, member: discord.Member):
        """向用户发送私信，让用户选择兴趣标签以开始引导流程。"""
        try:
            guild_id = member.guild.id
            tags = db_manager.get_all_tags(guild_id)
            if not tags:
                log.warning(f"服务器 {member.guild.name} 已触发引导流程，但尚未配置任何兴趣标签。")
                return

            template = db_manager.get_message_template(guild_id, "welcome_message")
            embed = create_embed_from_template(
                template,
                member.guild,
                user=member,
                server_name=member.guild.name
            )

            view = InitialGuidanceView(self.bot, guild_id, tags)

            await member.send(embed=embed, view=view)

            db_manager.create_or_reset_user_progress(member.id, guild_id, status=config.USER_STATUS_PENDING_SELECTION)
            log.info(f"已向用户 {member.name} 发送标签选择私信。")

        except discord.Forbidden:
            log.warning(f"无法向用户 {member.name} 发送私信。")
        except Exception as e:
            log.error(f"开始引导流程时发生错误 (用户: {member.name}): {e}", exc_info=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(CoreLogic(bot))