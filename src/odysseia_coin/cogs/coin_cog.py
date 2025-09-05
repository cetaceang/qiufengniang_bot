import logging
import discord
from discord import app_commands
from discord.ext import commands

from src.odysseia_coin.service.coin_service import coin_service
from src.odysseia_coin.ui.shop_ui import ShopHomeView
from src import config

log = logging.getLogger(__name__)

class CoinCog(commands.Cog):
    """处理与类脑币相关的事件和命令"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """监听用户每日首次发言"""
        if message.author.bot:
            return

        # 排除特定命令前缀的消息，避免与命令冲突
        if hasattr(self.bot, 'command_prefix') and message.content.startswith(self.bot.command_prefix):
            return

        try:
            reward_granted = await coin_service.grant_daily_message_reward(message.author.id)
            if reward_granted:
                log.info(f"用户 {message.author.name} ({message.author.id}) 获得了每日首次发言奖励。")
        except Exception as e:
            log.error(f"处理用户 {message.author.id} 的每日发言奖励时出错: {e}", exc_info=True)

    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread):
        """监听在特定论坛频道发帖的事件"""
        # 从配置文件中获取需要奖励的论坛频道ID列表
        if not config.COIN_REWARD_FORUM_CHANNEL_IDS:
            return

        if thread.parent_id in config.COIN_REWARD_FORUM_CHANNEL_IDS:
            try:
                # on_thread_create 事件没有直接的发帖者信息，需要从审计日志或起始消息获取
                # 为了简单起见，我们假设起始消息的作者就是发帖者
                # 注意：这在缓存不足时可能不总是可靠
                start_message = await thread.fetch_message(thread.id)
                if start_message and start_message.author:
                    author = start_message.author
                    if author.bot:
                        return
                        
                    reason = f"在频道 {thread.parent.name} 发布新帖"
                    new_balance = await coin_service.add_coins(author.id, 100, reason)
                    log.info(f"用户 {author.name} ({author.id}) 因在特定频道发帖获得 100 类脑币。新余额: {new_balance}")
                    
                    # 可以在帖子下发送一条祝贺消息
                    await thread.send(f"🎉 恭喜 {author.mention}！在这里发布新帖获得了 100 类脑币！", silent=True)

            except discord.NotFound:
                log.warning(f"无法为帖子 {thread.id} 找到起始消息，无法发放奖励。")
            except Exception as e:
                log.error(f"处理帖子 {thread.id} 的发帖奖励时出错: {e}", exc_info=True)

    @app_commands.command(name="类脑商店", description="打开商店，购买商品。")
    async def shop(self, interaction: discord.Interaction):
        """斜杠命令：打开商店"""
        await interaction.response.defer(ephemeral=True)
        try:
            balance = await coin_service.get_balance(interaction.user.id)
            view = ShopHomeView(interaction.user, balance)
            
            embed = discord.Embed(
                title="欢迎来到类脑商店!",
                description="选择你想为谁购买商品。",
                color=discord.Color.gold()
            )
            embed.set_footer(text=f"你当前的余额: {balance} 类脑币")
            
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            view.interaction = interaction

        except Exception as e:
            log.error(f"打开商店时出错: {e}", exc_info=True)
            await interaction.followup.send("打开商店时发生错误，请稍后再试。", ephemeral=True)

    @app_commands.command(name="admin_add_coins", description="【管理员】为指定用户添加类脑币。")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        user="选择一个用户",
        amount="要添加的金额"
    )
    async def admin_add_coins(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        amount: int
    ):
        """管理员命令：为用户添加类脑币"""
        if amount <= 0:
            await interaction.response.send_message("❌ 金额必须是正数。", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        try:
            reason = f"由管理员 {interaction.user.name} 添加"
            new_balance = await coin_service.add_coins(user.id, amount, reason)
            
            embed = discord.Embed(
                title="💰 类脑币添加成功",
                description=f"已成功为用户 {user.mention} 添加了 **{amount}** 类脑币。",
                color=discord.Color.green()
            )
            embed.add_field(name="操作人", value=interaction.user.mention, inline=True)
            embed.add_field(name="新余额", value=f"{new_balance}", inline=True)
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            log.info(f"管理员 {interaction.user.name} 为用户 {user.name} 添加了 {amount} 类脑币。")

        except Exception as e:
            log.error(f"管理员 {interaction.user.name} 添加类脑币时出错: {e}", exc_info=True)
            await interaction.followup.send(f"❌ 操作失败，发生内部错误：{e}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(CoinCog(bot))
    log.info("类脑币 Cog 已加载。")
