import discord
import logging
from typing import Dict, Any

# 导入 WorldBookService
from src.chat.features.world_book.services.world_book_service import world_book_service

log = logging.getLogger(__name__)

# 定义可用的类别列表
AVAILABLE_CATEGORIES = [
    "社区信息",
    "社区文化",
    "社区大事件",
    "俚语"
]

class WorldBookContributionModal(discord.ui.Modal, title="贡献知识"):
    """用于用户提交世界书知识条目的模态窗口"""
    
    def __init__(self):
        super().__init__()
        
        # 类别输入框
        self.category_input = discord.ui.TextInput(
            label="类别",
            placeholder=f"请输入类别，例如：{', '.join(AVAILABLE_CATEGORIES)}",
            max_length=50,
            required=True
        )
        self.add_item(self.category_input)
        
        # 标题输入框
        self.title_input = discord.ui.TextInput(
            label="标题",
            placeholder="请输入知识条目的标题",
            max_length=100,
            required=True
        )
        self.add_item(self.title_input)
        
        # 内容输入框
        self.content_input = discord.ui.TextInput(
            label="内容",
            placeholder="请输入详细内容",
            style=discord.TextStyle.paragraph,
            max_length=2000,
            required=True
        )
        self.add_item(self.content_input)
        
    async def on_submit(self, interaction: discord.Interaction):
        """当用户提交模态窗口时调用"""
        # 获取用户输入的值
        category = self.category_input.value.strip()
        title = self.title_input.value.strip()
        content = self.content_input.value.strip()
        
        # 基本验证
        if not category:
            await interaction.response.send_message("类别不能为空。", ephemeral=True)
            return
        
        # 验证类别是否在可用列表中
        if category not in AVAILABLE_CATEGORIES:
            await interaction.response.send_message(f"无效的类别。请从以下选项中选择: {', '.join(AVAILABLE_CATEGORIES)}", ephemeral=True)
            return
            
        if not title:
            await interaction.response.send_message("标题不能为空。", ephemeral=True)
            return
            
        if not content:
            await interaction.response.send_message("内容不能为空。", ephemeral=True)
            return
            
        # 调用 WorldBookService 的 add_general_knowledge 方法保存数据
        success = world_book_service.add_general_knowledge(
            title=title,
            name=title,  # 使用标题作为名称
            content_text=content,
            category_name=category,
            contributor_id=interaction.user.id
        )
        
        # 根据保存结果发送相应的消息
        if success:
            await interaction.response.send_message(
                f"感谢您的贡献！您的知识条目已成功提交。\n\n类别: {category}\n标题: {title}\n内容: {content[:100]}{'...' if len(content) > 100 else ''}",
                ephemeral=True
            )
            log.info(f"用户 {interaction.user.id} 成功提交了知识条目: category={category}, title={title}")

            # 构建并发送公共 embed 面板
            embed = discord.Embed(
                title="✨ 新的世界之书贡献！",
                description=f"**{interaction.user.display_name}** 提交了一个新的知识条目！",
                color=discord.Color.blue()
            )
            embed.add_field(name="类别", value=category, inline=True)
            embed.add_field(name="标题", value=title, inline=False)
            embed.add_field(name="内容预览", value=content[:500] + ('...' if len(content) > 500 else ''), inline=False) # 限制内容长度
            embed.set_footer(text=f"贡献者ID: {interaction.user.id}")
            embed.timestamp = interaction.created_at

            # 在当前频道发送 embed
            await interaction.channel.send(embed=embed)

        else:
            await interaction.response.send_message(
                "很抱歉，提交知识条目时出现了问题。请稍后再试。",
                ephemeral=True
            )
            log.error(f"用户 {interaction.user.id} 提交知识条目失败: category={category}, title={title}")