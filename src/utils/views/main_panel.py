# -*- coding: utf-8 -*-

import discord
from discord.ui import View, Button, button

# 导入各个子视图
from .tag_management import TagManagementView
from .path_configuration import PathConfigurationView
from .role_configuration import RoleConfigurationView
from .message_templates import MessageTemplatesView
from .deployment import DeploymentView

from ... import config # 导入配置文件以使用颜色

class MainPanelView(View):
    """
    主管理面板视图，作为所有管理功能的导航中心。
    """
    def __init__(self, interaction: discord.Interaction):
        super().__init__(timeout=180) # 设置超时时间
        self.interaction = interaction

    async def on_timeout(self):
        # 视图超时后禁用所有按钮
        for item in self.children:
            item.disabled = True
        try:
            await self.interaction.edit_original_response(view=self)
        except discord.NotFound:
            pass # 如果消息被删除则忽略

    @staticmethod
    def get_main_embed(guild: discord.Guild) -> discord.Embed:
        """生成主面板的 Embed"""
        embed = discord.Embed(
            title=f"⚙️ {guild.name} 新人引导管理面板",
            description="欢迎使用统一管理面板。请通过下方的按钮选择您要配置的项目。",
            color=config.EMBED_COLOR_INFO
        )
        embed.add_field(name="🏷️ 标签管理", value="创建、编辑和删除用于分类的兴趣标签。", inline=True)
        embed.add_field(name="🗺️ 路径设置", value="为每个标签关联具体的引导频道或帖子。", inline=True)
        embed.add_field(name="🛂 身份组配置", value="设置哪些身份组会触发新成员引导。", inline=True)
        embed.add_field(name="✉️ 消息模板", value="自定义引导流程中发送给用户的消息。", inline=True)
        embed.add_field(name="🚀 一键部署", value="将配置好的引导面板自动部署到指定位置。", inline=True)
        embed.add_field(name="📝 频道消息设置", value="为引导路径中的特定频道配置专属的临时消息。", inline=True)
        embed.set_footer(text="Odysseia Guidance System")
        return embed

    # --- 按钮回调 ---

    @button(label="标签管理", style=discord.ButtonStyle.secondary, emoji="🏷️", row=0)
    async def manage_tags(self, interaction: discord.Interaction, button: Button):
        # 切换到标签管理视图
        await interaction.response.defer() # 延迟响应，防止超时
        view = TagManagementView(self.interaction)
        embed = view.get_embed(interaction.guild, view.tags)
        await interaction.edit_original_response(embed=embed, view=view)

    @button(label="路径设置", style=discord.ButtonStyle.secondary, emoji="🗺️", row=0)
    async def configure_paths(self, interaction: discord.Interaction, button: Button):
        # 切换到路径设置视图
        await interaction.response.defer()
        view = PathConfigurationView(self.interaction)
        embed = view.get_embed(interaction.guild, None, view.tags, [])
        await interaction.edit_original_response(embed=embed, view=view)

    @button(label="身份组配置", style=discord.ButtonStyle.secondary, emoji="🛂", row=1)
    async def configure_roles(self, interaction: discord.Interaction, button: Button):
        """打开身份组配置视图"""
        await interaction.response.defer()
        view = RoleConfigurationView(self.interaction)
        embed = view.get_embed(interaction.guild, view.trigger_roles)
        await interaction.edit_original_response(embed=embed, view=view)

    @button(label="消息模板", style=discord.ButtonStyle.secondary, emoji="✉️", row=1)
    async def configure_templates(self, interaction: discord.Interaction, button: Button):
        """打开消息模板配置视图"""
        await interaction.response.defer()
        view = MessageTemplatesView(self.interaction)
        embed = view.get_embed(interaction.guild, view.templates)
        await interaction.edit_original_response(embed=embed, view=view)

    @button(label="频道消息设置", style=discord.ButtonStyle.secondary, emoji="📝", row=2)
    async def configure_channel_messages(self, interaction: discord.Interaction, button: Button):
        """打开频道专属消息配置视图"""
        from .channel_message_config import ChannelMessageConfigView
        await interaction.response.defer()
        view = ChannelMessageConfigView(self.interaction)
        embed = await view.get_config_list_embed() # 异步获取 embed
        await interaction.edit_original_response(embed=embed, view=view)

    @button(label="一键部署", style=discord.ButtonStyle.success, emoji="🚀", row=2)
    async def deploy(self, interaction: discord.Interaction, button: Button):
        """打开部署视图"""
        await interaction.response.defer()
        
        # 创建部署视图，它会自己进行检查
        deployment_view = DeploymentView(self.interaction)
        
        # 从部署视图获取检查结果来生成 Embed
        embed = DeploymentView.get_embed(
            interaction.guild,
            deployment_view.checks_passed,
            deployment_view.check_results
        )
        
        await interaction.edit_original_response(embed=embed, view=deployment_view)