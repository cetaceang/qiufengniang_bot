# -*- coding: utf-8 -*-

import discord
from discord.ui import View, Button, button, ChannelSelect
import logging
from typing import Dict, List, Tuple

from ...utils.database import db_manager
from .ui_elements import BackButton
from .channel_panel import PermanentPanelView # 这是我们要部署的用户端视图
from ... import config

log = logging.getLogger(__name__)

class DeploymentView(View):
    """处理批量部署频道专属消息的视图"""

    def __init__(self, main_interaction: discord.Interaction):
        super().__init__(timeout=180)
        self.main_interaction = main_interaction
        self.guild = main_interaction.guild

        # 运行部署前检查
        self.checks_passed, self.check_results = self.run_pre_deployment_checks()

        # 添加返回按钮
        self.add_item(BackButton())
        
        # 添加部署按钮
        self.add_item(DeployAllButton(disabled=not self.checks_passed))

    def run_pre_deployment_checks(self) -> Tuple[bool, Dict[str, Tuple[bool, str]]]:
        """执行部署前的所有检查。"""
        guild_id = self.guild.id
        results = {}
        
        # 检查 1: 是否至少有一个配置好的频道消息
        channel_configs = db_manager.get_all_channel_messages(guild_id)
        # 进一步筛选，确保至少有一个配置包含永久消息
        valid_configs = [c for c in channel_configs if c.get('permanent_message_data')]
        results["channel_configs"] = (bool(valid_configs), f"{len(valid_configs)} 个地点已配置")

        # 检查 2: 机器人是否拥有必要的权限 (这是一个概括性检查)
        # 实际部署时会进行更详细的逐个频道权限检查
        perms = self.guild.me.guild_permissions
        has_perms = perms.send_messages and perms.embed_links and perms.manage_messages
        results["permissions"] = (has_perms, "基本权限充足" if has_perms else "缺少关键权限")

        overall_result = all(res[0] for res in results.values())
        return overall_result, results

    @staticmethod
    def get_embed(guild: discord.Guild, checks_passed: bool, check_results: Dict) -> discord.Embed:
        """生成部署视图的 Embed"""
        if checks_passed:
            title = "✅ 准备就绪，可以部署"
            description = "所有前置检查均已通过。\n点击下方按钮，机器人将开始向所有已配置的频道部署或更新其专属的永久引导消息。"
            color = config.EMBED_COLOR_SUCCESS
        else:
            title = "⚠️ 部署前检查失败"
            description = "部分条件不满足，无法进行部署。请根据以下提示完成配置。"
            color = config.EMBED_COLOR_WARNING

        embed = discord.Embed(title=title, description=description, color=color)

        check_map = {
            "channel_configs": "📝 地点消息配置",
            "permissions": "🤖 机器人权限"
        }
        for key, (passed, status_text) in check_results.items():
            emoji = "✅" if passed else "❌"
            embed.add_field(name=f"{emoji} {check_map.get(key, key)}", value=f"状态: {status_text}", inline=True)
        
        embed.set_footer(text="部署过程可能需要一些时间，请耐心等待。")
        return embed

# --- UI 组件 ---

class DeployAllButton(Button):
    """确认部署所有频道消息的按钮"""
    def __init__(self, disabled: bool):
        super().__init__(label="🚀 一键部署所有地点", style=discord.ButtonStyle.success, row=1, disabled=disabled)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        guild = interaction.guild
        all_configs = db_manager.get_all_channel_messages(guild.id)
        
        # 筛选出需要部署的配置（即包含永久消息的配置）
        deploy_targets = [c for c in all_configs if c.get('permanent_message_data')]

        if not deploy_targets:
            await interaction.followup.send("❌ 没有找到任何已配置永久消息的地点可供部署。", ephemeral=True)
            return

        success_count = 0
        fail_count = 0
        report_lines = []

        for config_item in deploy_targets:
            channel_id = config_item['channel_id']
            channel = guild.get_channel_or_thread(channel_id)

            if not channel:
                report_lines.append(f"❌ **未知地点 (ID: {channel_id})**: 跳过部署。")
                fail_count += 1
                continue

            # 检查频道权限
            if not channel.permissions_for(guild.me).send_messages:
                report_lines.append(f"❌ **#{channel.name}**: 权限不足，无法在此处发送消息。")
                fail_count += 1
                continue

            try:
                # 尝试删除旧消息
                old_message_id = config_item.get('deployed_message_id')
                if old_message_id:
                    try:
                        old_message = await channel.fetch_message(old_message_id)
                        await old_message.delete()
                    except (discord.NotFound, discord.Forbidden):
                        # 如果旧消息删除失败，将数据库中的ID清空，避免产生孤立记录
                        db_manager.update_channel_deployment_id(channel_id, None)

                # 创建新消息
                perm_data = config_item['permanent_message_data']
                perm_embed = discord.Embed(
                    title=perm_data.get('title', f"欢迎来到 {channel.name}"),
                    description=perm_data.get('description', "请点击下方按钮了解详情。"),
                    color=config.EMBED_COLOR_INFO
                )
                
                # 设置页脚
                if perm_data.get('footer'):
                    perm_embed.set_footer(text=perm_data['footer'])
                
                # 设置缩略图
                if perm_data.get('image_url'):
                    perm_embed.set_thumbnail(url=perm_data['image_url'])

                # 注意：PermanentPanelView 需要是持久化视图，必须在机器人启动时注册
                view = PermanentPanelView()
                
                new_message = await channel.send(embed=perm_embed, view=view)
                
                # 更新数据库中的消息ID
                db_manager.update_channel_deployment_id(channel_id, new_message.id)
                
                report_lines.append(f"✅ **#{channel.name}**: [部署成功]({new_message.jump_url})")
                success_count += 1

            except Exception as e:
                log.error(f"部署到地点 {channel_id} 时出错: {e}", exc_info=True)
                report_lines.append(f"❌ **#{channel.name}**: 发生未知错误。")
                fail_count += 1
        
        # 发送最终报告
        report_embed = discord.Embed(
            title="部署完成",
            description=f"**总览: {success_count} 个成功, {fail_count} 个失败**",
            color=config.EMBED_COLOR_SUCCESS if fail_count == 0 else config.EMBED_COLOR_WARNING
        )
        report_embed.add_field(name="详细报告", value="\n".join(report_lines) or "无详细信息。", inline=False)
        
        await interaction.followup.send(embed=report_embed, ephemeral=True)
