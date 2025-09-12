import discord
import logging
from typing import List, Dict, Any

from src.chat.features.odysseia_coin.service.coin_service import coin_service, PERSONAL_MEMORY_ITEM_EFFECT_ID, WORLD_BOOK_CONTRIBUTION_ITEM_EFFECT_ID
from src.chat.features.personal_memory.services.personal_memory_service import personal_memory_service

log = logging.getLogger(__name__)

class SimpleShopView(discord.ui.View):
    """简化版的商店视图，直接显示所有商品"""
    def __init__(self, author: discord.Member, balance: int, items: List[Dict[str, Any]]):
        super().__init__(timeout=180)
        self.author = author
        self.balance = balance
        self.items = items
        self.selected_item_id = None
        
        # 按类别分组商品
        self.grouped_items = {}
        for item in items:
            category = item['category']
            if category not in self.grouped_items:
                self.grouped_items[category] = []
            self.grouped_items[category].append(item)

        # 添加类别选择下拉菜单
        self.add_item(CategorySelect(list(self.grouped_items.keys())))
        # 添加购买按钮和刷新余额按钮
        self.add_item(PurchaseButton())
        self.add_item(RefreshBalanceButton())

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if hasattr(self, 'interaction'):
            try:
                await self.interaction.edit_original_response(view=self)
            except:
                pass  # 忽略可能的错误，比如消息已被删除

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("这不是你的商店界面哦！", ephemeral=True)
            return False
        return True

    def create_shop_embed(self, purchase_message: str = None, category: str = None) -> discord.Embed:
        """创建商店的 Embed 消息"""
        description_text = "欢迎来到类脑商店！请选择你想要购买的商品。"
        if purchase_message:
            description_text = f"**{purchase_message}**\n\n" + description_text

        embed = discord.Embed(title="类脑商店", description=description_text, color=discord.Color.gold())
        
        if category:
            # 显示特定类别的商品
            embed.add_field(name=f"📁 {category}", value="请从下拉菜单中选择商品", inline=False)
        else:
            # 显示类别列表
            if self.items:
                categories = sorted(list(set(item['category'] for item in self.items)))
                categories_str = "\n".join([f"✨ **{cat}**" for cat in categories])
                embed.add_field(name="商品类别", value=categories_str, inline=False)
            else:
                embed.add_field(name="", value="商店暂时没有商品哦。", inline=False)
            
        embed.set_footer(text=f"你的余额: {self.balance} 类脑币")
        return embed

class CategorySelect(discord.ui.Select):
    """类别选择下拉菜单"""
    def __init__(self, categories: List[str]):
        options = [discord.SelectOption(
            label=category,
            value=category,
            description=f"浏览 {category} 类别的商品",
            emoji="📁"
        ) for category in categories]
        
        super().__init__(
            placeholder="选择一个商品类别...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        selected_category = self.values[0]
        # 创建商品选择下拉菜单
        item_select = ItemSelect(selected_category, self.view.grouped_items[selected_category])
        
        # 更新视图，移除类别选择，添加商品选择
        self.view.clear_items()
        self.view.add_item(item_select)
        self.view.add_item(BackToCategoriesButton())
        self.view.add_item(PurchaseButton())
        self.view.add_item(RefreshBalanceButton())
        
        # 更新嵌入消息，显示选中的类别
        new_embed = self.view.create_shop_embed(category=selected_category)
        await interaction.response.edit_message(embed=new_embed, view=self.view)

class ItemSelect(discord.ui.Select):
    """商品选择下拉菜单"""
    def __init__(self, category: str, items: List[Dict[str, Any]]):
        options = []
        for item in items:
            options.append(discord.SelectOption(
                label=item['name'],
                value=str(item['item_id']),
                description=f"{item['price']} 类脑币 - {item['description']}",
                emoji="🛒"
            ))
        
        # 确保选项数量不超过25个（Discord的限制）
        options = options[:25]
        
        super().__init__(
            placeholder=f"选择 {category} 中的商品...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        selected_value = self.values[0]
        self.view.selected_item_id = int(selected_value)
        await interaction.response.defer() # 延迟响应，避免"此互动失败"

class BackToCategoriesButton(discord.ui.Button):
    """返回类别选择按钮"""
    def __init__(self):
        super().__init__(label="返回类别", style=discord.ButtonStyle.secondary, emoji="⬅️")

    async def callback(self, interaction: discord.Interaction):
        # 重新创建类别选择视图
        self.view.clear_items()
        self.view.add_item(CategorySelect(list(self.view.grouped_items.keys())))
        self.view.add_item(PurchaseButton())
        self.view.add_item(RefreshBalanceButton())
        
        # 更新嵌入消息，回到类别列表
        new_embed = self.view.create_shop_embed()
        await interaction.response.edit_message(embed=new_embed, view=self.view)
class PurchaseButton(discord.ui.Button):
    """购买按钮"""
    def __init__(self):
        super().__init__(label="购买", style=discord.ButtonStyle.success, emoji="💰")

    async def callback(self, interaction: discord.Interaction):
        # 检查是否选择了商品
        if self.view.selected_item_id is None:
            await interaction.response.send_message("请先从下拉菜单中选择一个商品。", ephemeral=True)
            return

        # 获取选择的商品
        selected_item = None
        for item in self.view.items:
            if item['item_id'] == self.view.selected_item_id:
                selected_item = item
                break
                
        if not selected_item:
            await interaction.response.send_message("选择的商品无效。", ephemeral=True)
            return

        # 执行购买逻辑
        # 不再使用 defer 和 followup，而是直接处理并更新主界面
        try:
            success, message, _, should_show_modal = await coin_service.purchase_item(
                interaction.user.id,
                interaction.guild.id if interaction.guild else 0,
                selected_item['item_id']
            )
            
            # 如果购买成功且需要弹出模态框，则发送模态框
            if success and should_show_modal:
                # 检查购买的商品是否是"知识纸条"
                if selected_item['effect_id'] == WORLD_BOOK_CONTRIBUTION_ITEM_EFFECT_ID:
                    # 导入世界之书贡献模态框类
                    from src.chat.features.world_book.ui.contribution_modal import WorldBookContributionModal
                    modal = WorldBookContributionModal()
                    await interaction.response.send_modal(modal)
                else:
                    # 导入个人档案模态框类
                    from src.chat.features.personal_memory.ui.profile_modal import ProfileEditModal
                    modal = ProfileEditModal()
                    await interaction.response.send_modal(modal)
                return  # 不再执行后续的界面更新逻辑
            
            # 更新主界面（余额和商品列表）
            # 重新获取用户余额和商品列表
            self.view.balance = await coin_service.get_balance(interaction.user.id)
            self.view.items = await coin_service.get_all_items()
            
            # 重新按类别分组商品
            self.view.grouped_items = {}
            for item in self.view.items:
                category = item['category']
                if category not in self.view.grouped_items:
                    self.view.grouped_items[category] = []
                self.view.grouped_items[category].append(item)
            
            # 更新嵌入消息和视图
            new_embed = self.view.create_shop_embed(purchase_message=message)
            # 重新创建类别选择视图
            self.view.clear_items()
            self.view.add_item(CategorySelect(list(self.view.grouped_items.keys())))
            self.view.add_item(PurchaseButton())
            self.view.add_item(RefreshBalanceButton())
            
            # 编辑原始消息
            await interaction.response.edit_message(embed=new_embed, view=self.view)
            
        except Exception as e:
            log.error(f"处理购买商品 {selected_item['item_id']} 时出错: {e}", exc_info=True)
            # 即使出错也要更新界面
            self.view.balance = await coin_service.get_balance(interaction.user.id)
            self.view.items = await coin_service.get_all_items()
            
            error_message = "处理你的购买请求时发生了一个意想不到的错误。"
            new_embed = self.view.create_shop_embed(purchase_message=error_message)
            
            # 重新按类别分组商品
            self.view.grouped_items = {}
            for item in self.view.items:
                category = item['category']
                if category not in self.view.grouped_items:
                    self.view.grouped_items[category] = []
                self.view.grouped_items[category].append(item)
            
            self.view.clear_items()
            self.view.add_item(CategorySelect(list(self.view.grouped_items.keys())))
            self.view.add_item(PurchaseButton())
            self.view.add_item(RefreshBalanceButton())
            
            # 重新显示商店界面
            await interaction.response.edit_message(embed=new_embed, view=self.view)

class RefreshBalanceButton(discord.ui.Button):
    """刷新余额按钮"""
    def __init__(self):
        super().__init__(label="刷新余额", style=discord.ButtonStyle.secondary, emoji="🔄")

    async def callback(self, interaction: discord.Interaction):
        # 重新获取用户余额
        self.view.balance = await coin_service.get_balance(interaction.user.id)
        
        # 更新嵌入消息和视图
        new_embed = self.view.create_shop_embed()
        # 重新创建类别选择视图
        self.view.clear_items()
        self.view.add_item(CategorySelect(list(self.view.grouped_items.keys())))
        self.view.add_item(PurchaseButton())
        self.view.add_item(RefreshBalanceButton())
        
        # 编辑原始消息
        await interaction.response.edit_message(embed=new_embed, view=self.view)