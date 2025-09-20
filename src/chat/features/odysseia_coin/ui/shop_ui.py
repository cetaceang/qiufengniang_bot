import discord
import logging
import asyncio
import uuid
from typing import List, Dict, Any

from discord.ext import commands

from src.chat.features.odysseia_coin.service.coin_service import coin_service, PERSONAL_MEMORY_ITEM_EFFECT_ID, WORLD_BOOK_CONTRIBUTION_ITEM_EFFECT_ID, COMMUNITY_MEMBER_UPLOAD_EFFECT_ID
from src.chat.features.personal_memory.services.personal_memory_service import personal_memory_service
from src.chat.features.affection.service.gift_service import GiftService
from src.chat.features.affection.service.affection_service import affection_service
from src.chat.services.gemini_service import gemini_service

log = logging.getLogger(__name__)

class SimpleShopView(discord.ui.View):
    """简化版的商店视图，直接显示所有商品"""
    def __init__(self, bot: commands.Bot, author: discord.Member, balance: int, items: List[Dict[str, Any]]):
        super().__init__(timeout=180)
        self.bot = bot
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
        if self.view.selected_item_id is None:
            await interaction.response.send_message("请先从下拉菜单中选择一个商品。", ephemeral=True)
            return

        selected_item = next((item for item in self.view.items if item['item_id'] == self.view.selected_item_id), None)
        if not selected_item:
            await interaction.response.send_message("选择的商品无效。", ephemeral=True)
            return

        item_effect = selected_item.get('effect_id')

        # --- 新的个人记忆商品购买流程 ---
        if item_effect == PERSONAL_MEMORY_ITEM_EFFECT_ID:
            await self.handle_personal_memory_purchase(interaction, selected_item)
            return

        # --- 其他模态框购买流程 (保持原样) ---
        modal_effects = [
            WORLD_BOOK_CONTRIBUTION_ITEM_EFFECT_ID,
            COMMUNITY_MEMBER_UPLOAD_EFFECT_ID
        ]
        if item_effect in modal_effects:
            await self.handle_standard_modal_purchase(interaction, selected_item)
            return

        # --- 普通商品购买流程 ---
        await self.handle_standard_purchase(interaction, selected_item)

    async def handle_personal_memory_purchase(self, interaction: discord.Interaction, item: Dict[str, Any]):
        """处理个人记忆商品的购买，采用先开模态框后扣款的逻辑"""
        # 1. 检查余额
        current_balance = await coin_service.get_balance(interaction.user.id)
        if current_balance < item['price']:
            await interaction.response.send_message(f"你的余额不足！需要 {item['price']} 类脑币，但你只有 {current_balance}。", ephemeral=True)
            return

        # 2. 创建一个带唯一ID的模态框
        from src.chat.features.personal_memory.ui.profile_modal import ProfileEditModal
        unique_id = f"personal_profile_edit_modal_{uuid.uuid4()}"
        modal = ProfileEditModal(custom_id=unique_id)
        await interaction.response.send_modal(modal)

        try:
            # 3. 等待模态框提交
            modal_interaction: discord.Interaction = await self.view.bot.wait_for(
                "interaction",
                check=lambda i: i.type == discord.InteractionType.modal_submit and i.data.get("custom_id") == unique_id,
                timeout=300.0  # 5分钟超时
            )
            
            # 4. 用户提交后，先扣款
            await modal_interaction.response.defer(ephemeral=True)
            
            success, message, new_balance, _, _ = await coin_service.purchase_item(
                interaction.user.id,
                interaction.guild.id if interaction.guild else 0,
                item['item_id']
            )

            if not success:
                await modal_interaction.followup.send(f"购买失败：{message}", ephemeral=True)
                return

            # 5. 扣款成功后，保存个人档案
            components = modal_interaction.data.get('components', [])
            values_by_id = {
                comp['components']['custom_id']: comp['components']['value']
                for comp in components if comp.get('components')
            }
            profile_data = {
                'name': values_by_id.get('name', ''),
                'personality': values_by_id.get('personality', ''),
                'background': values_by_id.get('background', ''),
                'preferences': values_by_id.get('preferences', '')
            }
            await personal_memory_service.save_user_profile(interaction.user.id, profile_data)
            
            embed = discord.Embed(
                title="个人档案已保存",
                description=f"你的个人档案已成功保存！本次消费 **{item['price']}** 类脑币。",
                color=discord.Color.green()
            )
            await modal_interaction.followup.send(embed=embed, ephemeral=True)

            # 6. 更新商店界面
            self.view.balance = new_balance
            new_embed = self.view.create_shop_embed()
            await interaction.edit_original_response(embed=new_embed, view=self.view)

        except asyncio.TimeoutError:
            # 7. 用户未提交，超时处理
            await interaction.followup.send("由于你长时间未操作，购买已自动取消。", ephemeral=True)
        except Exception as e:
            log.error(f"处理个人记忆商品购买时出错: {e}", exc_info=True)
            if not interaction.response.is_done():
                await interaction.followup.send("处理你的购买请求时发生了一个意想不到的错误。", ephemeral=True)

    async def handle_standard_modal_purchase(self, interaction: discord.Interaction, item: Dict[str, Any]):
        """处理需要弹出模态框的商品的购买（旧逻辑）"""
        success, message, new_balance, should_show_modal, _ = await coin_service.purchase_item(
            interaction.user.id,
            interaction.guild.id if interaction.guild else 0,
            item['item_id']
        )

        if success and should_show_modal:
            modal_map = {
                WORLD_BOOK_CONTRIBUTION_ITEM_EFFECT_ID: "src.chat.features.world_book.ui.contribution_modal.WorldBookContributionModal",
                COMMUNITY_MEMBER_UPLOAD_EFFECT_ID: "src.chat.features.community_member.ui.community_member_modal.CommunityMemberUploadModal",
            }
            modal_path = modal_map.get(item['effect_id'])
            if modal_path:
                parts = modal_path.split('.')
                module_path, class_name = '.'.join(parts[:-1]), parts[-1]
                module = __import__(module_path, fromlist=[class_name])
                ModalClass = getattr(module, class_name)
                await interaction.response.send_modal(ModalClass())
            
            # 更新商店界面
            self.view.balance = new_balance
            new_embed = self.view.create_shop_embed()
            await interaction.edit_original_response(embed=new_embed, view=self.view)
        elif not success:
            await interaction.response.send_message(message, ephemeral=True)


    async def handle_standard_purchase(self, interaction: discord.Interaction, item: Dict[str, Any]):
        """处理普通商品的购买"""
        await interaction.response.defer(ephemeral=True)
        try:
            success, message, new_balance, _, should_generate_gift_response = await coin_service.purchase_item(
                interaction.user.id,
                interaction.guild.id if interaction.guild else 0,
                item['item_id']
            )

            final_message = message
            if success and should_generate_gift_response:
                gift_service = GiftService(gemini_service, affection_service)
                try:
                    ai_response = await gift_service.generate_gift_response(interaction.user, item['name'])
                    final_message += f"\n\n{ai_response}"
                except Exception as e:
                    log.error(f"为礼物 {item['name']} 生成AI回应时出错: {e}")
                    final_message += "\n\n（AI 在想感谢语时遇到了点小麻烦，但你的心意已经收到了！）"
            
            try:
                await interaction.followup.send(final_message, ephemeral=True)
            except discord.errors.NotFound:
                log.warning(f"Followup failed for user {interaction.user.id}, sending DM as fallback.")
                try:
                    await interaction.user.send(f"你的购买已完成！\n\n{final_message}")
                except discord.errors.Forbidden:
                    log.error(f"Failed to send DM to user {interaction.user.id} as a fallback.")


            if success:
                self.view.balance = new_balance
                new_embed = self.view.create_shop_embed()
                await interaction.edit_original_response(embed=new_embed, view=self.view)

        except Exception as e:
            log.error(f"处理购买商品 {item['item_id']} 时出错: {e}", exc_info=True)
            if not interaction.response.is_done():
                await interaction.followup.send("处理你的购买请求时发生了一个意想不到的错误。", ephemeral=True)

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