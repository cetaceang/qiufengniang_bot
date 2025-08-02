# -*- coding: utf-8 -*-

import discord
from discord.ui import View, Button, button
import json
import logging

from ...utils.database import db_manager
from ... import config

log = logging.getLogger(__name__)

class PermanentPanelView(View):
    """
    部署在频道中的永久消息面板。
    这个视图的实例对于所有用户都是一样的，但它的回调函数会根据点击的用户来动态响应。
    """
    def __init__(self):
        # timeout=None 确保这个视图永不过期
        # custom_id 是必需的，以便在机器人重启后 discord 能够重新关联视图
        super().__init__(timeout=None)

    @button(label="了解详情 & 前往下一步", style=discord.ButtonStyle.primary, emoji="ℹ️", custom_id="show_channel_details")
    async def show_details(self, interaction: discord.Interaction, button: Button):
        """
        当用户点击按钮时，显示一个临时的、包含详细信息和下一步链接的消息。
        """
        try:
            await interaction.response.defer(ephemeral=True)

            # 1. 获取用户进度
            user_progress = db_manager.get_user_progress(interaction.user.id, interaction.guild.id)
            if not user_progress or not user_progress['generated_path_json']:
                await interaction.followup.send("🤔 看起来你还没有开始引导流程，或者你的进度已过期。请重新从引导开始。", ephemeral=True)
                return

            # 2. 获取当前频道的专属消息配置
            channel_config = db_manager.get_channel_message(interaction.channel.id)
            if not channel_config or not channel_config.get('temporary_message_data'):
                await interaction.followup.send("❌ 此频道的详细信息目前还没有配置哦。", ephemeral=True)
                return

            # 3. 解析路径和当前步骤
            user_path = json.loads(user_progress['generated_path_json'])
            current_step_index = user_progress['current_step'] - 1  # DB is 1-based, index is 0-based

            # [新] 安全检查：确保用户在正确的步骤上
            # 新的 user_path 是一个字典列表，所以我们需要比较 location_id
            if current_step_index < 0 or current_step_index >= len(user_path) or user_path[current_step_index]['location_id'] != interaction.channel.id:
                # 尝试找到用户路径中这个频道的正确步骤
                try:
                    # 使用生成器表达式和 next() 来查找第一个匹配的索引
                    correct_step_index = next(i for i, step in enumerate(user_path) if step['location_id'] == interaction.channel.id)
                    db_manager.update_user_progress(interaction.user.id, interaction.guild.id, current_step=correct_step_index + 1)
                    current_step_index = correct_step_index
                except StopIteration:  # 如果 next() 找不到元素，会引发 StopIteration
                    await interaction.followup.send("🤔 你似乎偏离了为你规划的引导路径。请尝试返回上一步或重新开始引导。", ephemeral=True)
                    return

            # 4. 准备临时消息内容
            temp_data = channel_config['temporary_message_data']
            temp_embed = discord.Embed(
                title=temp_data.get('title', f"关于 {interaction.channel.name} 的详细信息"),
                description=temp_data.get('description', "管理员还没有填写详细介绍。"),
                color=config.EMBED_COLOR_SUCCESS
            )

            # 5. 确定下一步并创建视图
            next_step_view = View(timeout=None) # 初始化一个空的、永不过期的视图

            if current_step_index + 1 < len(user_path):
                # 还有下一步
                next_channel_id = user_path[current_step_index + 1]['location_id']
                next_channel = interaction.guild.get_channel_or_thread(next_channel_id)

                if next_channel:
                    # --- 新逻辑：优先跳转到永久消息 ---
                    next_step_config = db_manager.get_channel_message(next_channel_id)
                    deployed_message_id = next_step_config.get('deployed_message_id') if next_step_config else None
                    
                    if deployed_message_id:
                        # 如果找到了已部署的消息ID，直接生成消息链接
                        next_step_url = f"https://discord.com/channels/{interaction.guild.id}/{next_channel_id}/{deployed_message_id}"
                    else:
                        # 备用方案：跳转到频道/帖子顶部
                        next_step_url = next_channel.jump_url

                    temp_embed.description = temp_embed.description.replace("{next_step_url}", next_step_url)
                    
                    # 直接添加按钮，并明确指出下一站的名称
                    next_step_view.add_item(Button(
                        label=f"前往下一站：{next_channel.name}",
                        style=discord.ButtonStyle.link,
                        url=next_step_url,
                        emoji="➡️"
                    ))

                    # 只有在确认有下一步时才更新进度
                    db_manager.update_user_progress(interaction.user.id, interaction.guild.id, current_step=current_step_index + 2)
                else:
                    # 找不到下一步频道
                    temp_embed.color = discord.Color.red()
                    temp_embed.description += (
                        f"\n\n**[路径配置错误]**\n"
                        f"无法找到引导路径中的下一个地点 (ID: `{next_channel_id}`) 。\n"
                        f"它可能已被删除，或者我没有权限访问它。\n"
                        f"请联系服务器管理员检查后台的引导路径设置。"
                    )
                    # 不添加任何按钮，用户无法继续
            else:
                # 这是最后一步
                temp_embed.description += f"\n\n{config.GUIDANCE_COMPLETION_MESSAGE}"
                # 不再添加任何按钮，一个空的视图即可
                
                # 将用户状态标记为完成
                db_manager.update_user_progress(interaction.user.id, interaction.guild.id, status="completed")

            # 无论如何，next_step_view 现在都是一个有效的 View 对象
            await interaction.followup.send(embed=temp_embed, view=next_step_view, ephemeral=True)

        except Exception as e:
            log.error(f"处理频道详情按钮时出错: {e}", exc_info=True)
            await interaction.followup.send("❌ 处理请求时发生了一个内部错误。", ephemeral=True)
