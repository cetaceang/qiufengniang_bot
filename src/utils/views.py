import json
import asyncio
# -*- coding: utf-8 -*-

import discord
import logging
from typing import List, Dict, Any

# 从我们自己的模块中导入
import config
from utils.database import db_manager
from utils.helpers import create_message_jump_url

log = logging.getLogger(__name__)

class TagSelect(discord.ui.Select):
    """
    一个下拉选择菜单，用于让用户选择他们感兴趣的标签。
    """
    def __init__(self, tags: List[Dict[str, Any]]):
        # tags 是一个从数据库查询出来的列表，每个元素是一个字典，包含 tag_id, tag_name, description
        
        options = [
            discord.SelectOption(
                label=tag['tag_name'],
                description=tag['description'] if 'description' in tag and tag['description'] else None,
                value=str(tag['tag_id']) # value 必须是字符串
            ) for tag in tags
        ]

        # min_values=1 确保用户至少选择一个
        super().__init__(
            placeholder="选择你感兴趣的领域...",
            min_values=1,
            max_values=len(options), # 最多可以选择所有标签
            options=options,
            custom_id="tag_selection_dropdown" # 添加一个 custom_id
        )

    async def callback(self, interaction: discord.Interaction):
        """当用户在下拉菜单中做出选择时被调用"""
        # 我们不需要在这里做任何事，因为我们将在用户点击“确认”按钮后统一处理
        # 但为了更好的用户体验，我们可以更新一下按钮的状态或发送一个临时的确认消息
        # 这里我们暂时保持简单，只响应交互以防止 Discord 报错
        await interaction.response.defer()


class TagSelectionView(discord.ui.View):
    """
    包含标签选择下拉菜单和确认/取消按钮的完整视图。
    这个视图将被发送到用户的私信中。
    """
    def __init__(self, user: discord.Member, tags: List[Dict[str, Any]]):
        # timeout 从 config.py 中读取
        super().__init__(timeout=config.VIEW_TIMEOUT)
        self.user = user
        self.selected_tags: List[str] = [] # 存储用户选择的 tag_id 列表

        # 1. 创建并添加下拉菜单
        self.tag_select_menu = TagSelect(tags)
        self.add_item(self.tag_select_menu)

        # 2. 创建并添加按钮 (在下一行添加)
        # 我们将在下面定义按钮的回调函数

    @discord.ui.button(label="确认选择", style=discord.ButtonStyle.success, custom_id="confirm_tags_button", row=1)
    async def confirm_button_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        """当用户点击“确认选择”按钮时被调用"""
        # 检查交互的用户是否是最初接收此消息的用户
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("抱歉，你不能为其他用户做选择。", ephemeral=True)
            return

        # 获取下拉菜单中选中的值
        self.selected_tags = self.tag_select_menu.values
        
        if not self.selected_tags:
            await interaction.response.send_message("请至少选择一个你感兴趣的标签！", ephemeral=True)
            return

        # 禁用所有组件，防止用户重复点击
        for item in self.children:
            item.disabled = True
        
        # 禁用所有组件，防止用户重复点击
        for item in self.children:
            item.disabled = True
        
        # 编辑原始消息以应用禁用的视图。
        # 这会立即让按钮变灰，防止重复点击，同时响应了交互，避免了任何中间状态消息。
        await interaction.response.edit_message(view=self)
        
        # 分发一个自定义事件，将处理逻辑解耦到 core_logic.py 中
        interaction.client.dispatch('guidance_tags_selected', interaction, self.user, self.selected_tags)
        
        log.info(f"用户 {self.user.name} (ID: {self.user.id}) 确认了标签选择: {self.selected_tags}。已分发事件。")
        
        # 停止视图的监听
        self.stop()

    @discord.ui.button(label="取消", style=discord.ButtonStyle.secondary, custom_id="cancel_guidance_button", row=1)
    async def cancel_button_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        """当用户点击“取消”按钮时被调用"""
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("抱歉，你不能为其他用户做选择。", ephemeral=True)
            return

        # 禁用所有组件
        for item in self.children:
            item.disabled = True
            
        # 编辑原始消息
        await interaction.response.edit_message(content="你已取消本次引导流程。如果想重新开始，请联系管理员为你重新分配引导身份组。", view=self)
        
        # 更新数据库中用户的状态为 'cancelled'
        db_manager.update_user_progress(self.user.id, self.user.guild.id, status=config.USER_STATUS_CANCELLED)
        
        log.info(f"用户 {self.user.name} (ID: {self.user.id}) 取消了引导流程。")
        self.stop()

    async def on_timeout(self):
        """当视图超时（用户长时间未操作）时被调用"""
        # 禁用所有组件
        for item in self.children:
            item.disabled = True
        
        # 编辑原始消息，告知用户已超时
        # self.message 是这条视图附着的消息
        if self.message:
            await self.message.edit(content="⌛ 由于你长时间未操作，本次引导流程已自动取消。如果想重新开始，请联系管理员为你重新分配引导身份组。", view=self)
        
        # 更新数据库中用户的状态为 'cancelled'
        db_manager.update_user_progress(self.user.id, self.user.guild.id, status=config.USER_STATUS_CANCELLED)

        log.warning(f"用户 {self.user.name} (ID: {self.user.id}) 的标签选择视图已超时，状态已更新为 cancelled。")

class GuidancePanelView(discord.ui.View):
    """
    部署在引导频道中的永久性视图。
    包含一个“查看详细介绍”的按钮。
    """
    def __init__(self):
        # 对于永久视图，timeout 必须设置为 None。
        # 机器人通过其内部组件的 custom_id 来重新识别并附加到旧消息上。
        super().__init__(timeout=None)

    @discord.ui.button(label="查看详细介绍", style=discord.ButtonStyle.primary, custom_id="show_details_button")
    async def show_details(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        当用户点击“查看详细介绍”按钮时的回调。
        这是整个引导流程中，用户在频道内进行交互的核心。
        """
        # 由于这是一个耗时操作（需要查询数据库），先 defer
        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            # 1. 查询用户进度
            user_progress = db_manager.get_user_progress(interaction.user.id, interaction.guild_id)
            if not user_progress or user_progress['status'] != config.USER_STATUS_IN_PROGRESS:
                await interaction.followup.send("你当前没有正在进行的引导流程，或流程已完成。", ephemeral=True)
                return
            
            # 2. 检查当前频道是否在用户的路径中
            generated_path = json.loads(user_progress['generated_path_json'])
            current_step_index = user_progress['current_step'] - 1
            
            if current_step_index >= len(generated_path) or interaction.channel.id != generated_path[current_step_index]:
                correct_channel_id = generated_path[current_step_index]
                await interaction.followup.send(
                    f"🤔 你似乎走错地方了哦！你的下一站应该是 <#{correct_channel_id}>。",
                    ephemeral=True
                )
                return

            # 3. 获取当前频道的临时消息配置
            panel_config = db_manager.get_panel_config(interaction.channel.id)
            if not panel_config or not panel_config['temp_message_data']:
                await interaction.followup.send("抱歉，此频道的详细介绍似乎还没有配置好。", ephemeral=True)
                return

            # 4. 发送临时消息
            temp_message_data = json.loads(panel_config['temp_message_data'])
            embed = discord.Embed.from_dict(temp_message_data)
            
            # 5. 准备“下一步”按钮或完成引导
            next_step_view = discord.ui.View()
            is_last_step = current_step_index == len(generated_path) - 1
            
            if not is_last_step:
                next_channel_id = generated_path[current_step_index + 1]
                next_channel = interaction.guild.get_channel(next_channel_id)
                if next_channel:
                    jump_url_next = create_message_jump_url(interaction.guild, next_channel, db_manager)
                    next_step_view.add_item(discord.ui.Button(
                        label=f"前往下一站: #{next_channel.name}",
                        style=discord.ButtonStyle.success,
                        url=jump_url_next
                    ))
                
                # 更新数据库中的进度
                db_manager.update_user_progress(interaction.user.id, interaction.guild_id, current_step=user_progress['current_step'] + 1)
                log.info(f"用户 {interaction.user.name} 已完成第 {user_progress['current_step']} 步，进入下一站。")

            await interaction.followup.send(embed=embed, view=next_step_view, ephemeral=True)

            # 6. 如果是最后一步，发送完成消息
            if is_last_step:
                db_manager.update_user_progress(interaction.user.id, interaction.guild_id, status=config.USER_STATUS_COMPLETED)
                
                guild_config = db_manager.get_guild_config(interaction.guild_id)
                completion_message = "恭喜你完成了所有引导！"
                if guild_config and guild_config['completion_message']:
                    completion_message = guild_config['completion_message'].format(user=interaction.user.mention, guild=interaction.guild.name)
                
                # 在发送完成消息前稍微等待一下，给用户阅读当前步骤内容的时间
                await asyncio.sleep(2)
                await interaction.followup.send(completion_message, ephemeral=True)
                log.info(f"用户 {interaction.user.name} 已完成所有引导步骤。")

        except Exception as e:
            log.error(f"处理引导面板点击时出错: {e}", exc_info=True)
            await interaction.followup.send("❌ 处理你的请求时发生内部错误。", ephemeral=True)