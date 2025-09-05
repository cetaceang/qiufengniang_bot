import discord
import logging
from typing import List, Dict, Any

from src.odysseia_coin.service.coin_service import coin_service

log = logging.getLogger(__name__)

# 商品类别定义
CATEGORIES = {
    "self": [
        {"label": "食品-给自己", "description": "购买给自己使用的消耗品。", "value": "食品-给自己", "emoji": "🍔"},
        {"label": "物品-给自己", "description": "购买给自己使用的物品。", "value": "物品-给自己", "emoji": "🎒"},
    ],
    "odysseia": [
        {"label": "食品-给类脑娘", "description": "买些好吃的送给类脑娘吧！", "value": "食品-给类脑娘", "emoji": "🍰"},
        {"label": "礼物-给类脑娘", "description": "各种各样的礼物，送给类脑娘。", "value": "礼物-给类脑娘", "emoji": "🎁"},
    ]
}

class ShopHomeView(discord.ui.View):
    """商店的初始主页视图"""
    def __init__(self, author: discord.Member, balance: int):
        super().__init__(timeout=180)
        self.author = author
        self.balance = balance
        self.add_item(PurchaseForButton("self", "为自己购买", "🍔"))
        self.add_item(PurchaseForButton("odysseia", "为类脑娘购买", "💖"))

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        # 尝试获取原始交互并编辑消息
        if hasattr(self, 'interaction'):
            await self.interaction.edit_original_response(view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("这不是你的商店界面哦！", ephemeral=True)
            return False
        return True

class PurchaseForButton(discord.ui.Button):
    """选择为谁购买的按钮"""
    def __init__(self, target: str, label: str, emoji: str):
        super().__init__(label=label, style=discord.ButtonStyle.primary, emoji=emoji)
        self.target = target

    async def callback(self, interaction: discord.Interaction):
        # 创建并发送商品类别选择视图
        view = ShopView(interaction.user, self.target)
        await view.update_view(interaction)

class ShopView(discord.ui.View):
    """商店的商品展示和购买视图"""
    def __init__(self, author: discord.Member, target: str):
        super().__init__(timeout=180)
        self.author = author
        self.target = target  # 'self' or 'odysseia'
        self.categories = CATEGORIES[self.target]
        self.current_category = self.categories[0]['value']
        self.author_balance = 0  # 将在 update_view 中更新
        self.add_item(CategorySelect(self, self.categories))
        self.add_item(BackButton())

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if hasattr(self, 'interaction'):
            await self.interaction.edit_original_response(view=self)

    async def update_view(self, interaction: discord.Interaction, is_back: bool = False):
        """根据当前选择的类别更新视图和消息"""
        self.author_balance = await coin_service.get_balance(self.author.id)
        
        # 清理旧项目
        self.clear_items()
        self.add_item(CategorySelect(self, self.categories))
        self.add_item(BackButton())

        items = await coin_service.get_items_by_category(self.current_category)
        
        if items:
            for item in items:
                self.add_item(PurchaseButton(item))
        
        embed = self.create_shop_embed(items)
        
        if is_back:
            # 如果是返回操作，不需要 defer
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            # 首次进入或切换分类
            if interaction.response.is_done():
                await interaction.edit_original_response(embed=embed, view=self)
            else:
                await interaction.response.edit_message(embed=embed, view=self)


    def create_shop_embed(self, items: List[Dict[str, Any]]) -> discord.Embed:
        """创建商店的 Embed 消息"""
        title = f"商店 - {self.current_category}"
        description = "请选择你想要购买的商品。" if items else "这个类别下暂时没有商品哦。"
        
        embed = discord.Embed(title=title, description=description, color=discord.Color.blurple())
        
        for item in items:
            embed.add_field(
                name=f"{item['name']} - {item['price']} 类脑币",
                value=item['description'],
                inline=False
            )
        
        embed.set_footer(text=f"你的余额: {self.author_balance} 类脑币")
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("这不是你的商店界面哦！", ephemeral=True)
            return False
        return True

class BackButton(discord.ui.Button):
    """返回主菜单的按钮"""
    def __init__(self):
        super().__init__(label="返回主菜单", style=discord.ButtonStyle.secondary, emoji="↩️", row=4)

    async def callback(self, interaction: discord.Interaction):
        balance = await coin_service.get_balance(interaction.user.id)
        home_view = ShopHomeView(interaction.user, balance)
        
        embed = discord.Embed(
            title="欢迎来到类脑商店!",
            description="选择你想为谁购买商品。",
            color=discord.Color.gold()
        )
        embed.set_footer(text=f"你当前的余额: {balance} 类脑币")
        
        await interaction.response.edit_message(embed=embed, view=home_view)

class CategorySelect(discord.ui.Select):
    """商品类别选择器"""
    def __init__(self, parent_view: ShopView, categories: List[Dict[str, str]]):
        self.parent_view = parent_view
        options = [discord.SelectOption(**cat) for cat in categories]
        super().__init__(placeholder="选择一个商品类别...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        self.parent_view.current_category = self.values[0]
        await self.parent_view.update_view(interaction)

class PurchaseButton(discord.ui.Button):
    """购买商品的按钮"""
    def __init__(self, item: Dict[str, Any]):
        self.item = item
        super().__init__(
            label=f"购买 {item['name']}",
            style=discord.ButtonStyle.green,
            custom_id=f"purchase_{item['item_id']}"
        )

    async def callback(self, interaction: discord.Interaction):
        # 不再使用 defer，因为我们需要根据购买结果决定如何响应
        # await interaction.response.defer(ephemeral=True)
        
        try:
            success, message, _ = await coin_service.purchase_item(
                interaction.user.id,
                interaction.guild.id,
                self.item['item_id']
            )
            
            # 购买失败时，只发送一个临时的 follow-up 消息，不更新主界面
            if not success:
                embed = discord.Embed(
                    title="购买失败",
                    description=message,
                    color=discord.Color.red()
                )
                # 使用 defer + followup 来避免 "already responded" 错误
                await interaction.response.defer(ephemeral=True, thinking=False)
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            # 购买成功，发送回执并更新主界面
            embed = discord.Embed(
                title="购买成功",
                description=message,
                color=discord.Color.green()
            )
            # 先 defer，避免超时
            await interaction.response.defer(ephemeral=True, thinking=False)
            await interaction.followup.send(embed=embed, ephemeral=True)

            # 更新主界面
            parent_view = self.view
            if isinstance(parent_view, ShopView):
                # 重新获取 embed 和 view
                parent_view.author_balance = await coin_service.get_balance(interaction.user.id)
                items = await coin_service.get_items_by_category(parent_view.current_category)
                shop_embed = parent_view.create_shop_embed(items)
                
                # 使用 edit_original_response 更新原始消息
                await interaction.edit_original_response(embed=shop_embed, view=parent_view)

        except Exception as e:
            log.error(f"处理购买商品 {self.item['item_id']} 时出错: {e}", exc_info=True)
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True, thinking=False)
            await interaction.followup.send("处理你的购买请求时发生了一个意想不到的错误。", ephemeral=True)