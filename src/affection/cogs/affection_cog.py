import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import time, timezone, timedelta
import logging

from src.affection.service.affection_service import affection_service
from src.utils.database import db_manager

log = logging.getLogger(__name__)

class AffectionCog(commands.Cog):
    """处理与好感度相关的用户命令。"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.affection_service = affection_service
        # 设置时区为 UTC+8
        self.beijing_tz = timezone(timedelta(hours=8))
        # 每天凌晨 00:05 执行
        self.daily_task.start()

    def cog_unload(self):
        self.daily_task.cancel()

    @tasks.loop(time=time(0, 5, tzinfo=timezone(timedelta(hours=8))))
    async def daily_task(self):
        """每日定时任务，用于处理好感度浮动和重置。"""
        log.info("开始执行每日好感度定时任务...")
        today_str = datetime.now(self.beijing_tz).date().isoformat()
        
        for guild in self.bot.guilds:
            try:
                # 1. 重置每日好感度获得量
                await db_manager.reset_daily_affection_gain(guild.id, today_str)
                log.info(f"已为服务器 {guild.id} 重置每日好感度上限。")

                # 2. 应用每日随机浮动
                await self.affection_service.apply_daily_fluctuation(guild.id)
                log.info(f"已为服务器 {guild.id} 应用每日好感度浮动。")

            except Exception as e:
                log.error(f"为服务器 {guild.id} 执行每日好感度任务时出错: {e}", exc_info=True)
        
        log.info("每日好感度定时任务执行完毕。")

    @app_commands.command(name="affection", description="查询你与AI的好感度状态。")
    async def affection(self, interaction: discord.Interaction):
        """处理好感度查询命令。"""
        await interaction.response.defer(ephemeral=True)
        
        user = interaction.user
        guild = interaction.guild

        if not guild:
            await interaction.followup.send("此命令只能在服务器中使用。", ephemeral=True)
            return

        try:
            status = await self.affection_service.get_affection_status(user.id, guild.id)
            
            embed = discord.Embed(
                title=f"{user.display_name} 与AI的好感度",
                color=discord.Color.pink()
            )
            embed.set_thumbnail(url=user.display_avatar.url)
            
            embed.add_field(name="当前等级", value=f"**{status['level_name']}**", inline=False)
            embed.add_field(name="好感度点数", value=str(status['points']), inline=True)
            embed.add_field(name="今日已获得", value=f"{status['daily_gain']} / {status['daily_cap']}", inline=True)
            
            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            await interaction.followup.send(f"查询好感度时出错: {e}", ephemeral=True)
            # 可以在这里添加更详细的日志记录
            print(f"Error in affection command: {e}")

    @app_commands.command(name="reset_all_affection", description="【管理员】重置所有用户的好感度为0")
    @app_commands.default_permissions(administrator=True)
    async def reset_all_affection(self, interaction: discord.Interaction):
        """重置服务器内所有用户的好感度"""
        await interaction.response.defer(ephemeral=True)
        
        if not interaction.guild:
            await interaction.followup.send("此命令只能在服务器中使用。", ephemeral=True)
            return
            
        try:
            reset_count = await db_manager.reset_all_affection_points(interaction.guild.id)
            
            await interaction.followup.send(
                f"操作成功！已将服务器内 {reset_count} 名用户的好感度重置为 0。",
                ephemeral=True
            )
            log.info(f"管理员 {interaction.user} 已重置服务器 {interaction.guild.id} 中所有用户的好感度。")

        except Exception as e:
            log.error(f"重置所有用户好感度时出错: {e}", exc_info=True)
            await interaction.followup.send("重置好感度时发生严重错误，请检查日志。", ephemeral=True)


    @app_commands.command(name="set_affection", description="【管理员】设置指定用户的好感度分数")
    @app_commands.describe(user="要修改好感度的用户", points="要设置的好感度分数")
    @app_commands.default_permissions(administrator=True)
    async def set_affection(self, interaction: discord.Interaction, user: discord.User, points: int):
        """设置单个用户的好感度分数"""
        await interaction.response.defer(ephemeral=True)
        
        if not interaction.guild:
            await interaction.followup.send("此命令只能在服务器中使用。", ephemeral=True)
            return
            
        try:
            # 直接调用 db_manager 更新好感度
            await db_manager.update_affection(
                user_id=user.id,
                guild_id=interaction.guild.id,
                affection_points=points
            )
            
            # 获取更新后的状态以供显示
            new_status = await self.affection_service.get_affection_status(user.id, interaction.guild.id)
            
            await interaction.followup.send(
                f"操作成功！已将用户 {user.mention} 的好感度设置为 **{points}**。\n"
                f"当前等级为：**{new_status['level_name']}**。",
                ephemeral=True
            )
            log.info(f"管理员 {interaction.user} 已将用户 {user.id} 的好感度设置为 {points}。")

        except Exception as e:
            log.error(f"设置用户 {user.id} 好感度时出错: {e}", exc_info=True)
            await interaction.followup.send("设置好感度时发生严重错误，请检查日志。", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AffectionCog(bot))