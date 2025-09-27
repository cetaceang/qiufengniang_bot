import discord
from discord import app_commands
from discord.ext import commands
import re

from src.chat.config.chat_config import CONFESSION_CONFIG, CONFESSION_PROMPT
from src.chat.config.prompts import SYSTEM_PROMPT
from src.chat.features.affection.service.affection_service import AffectionService
from src.chat.features.affection.service.confession_service import ConfessionService
from src.chat.services.gemini_service import gemini_service
from src.chat.utils.prompt_utils import replace_emojis

class ConfessionCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.affection_service = AffectionService()
        self.confession_service = ConfessionService()

    @app_commands.command(name="忏悔", description="向类脑娘忏悔，或许能让她对你的态度改观一些?")
    @app_commands.guild_only()
    @app_commands.rename(content='忏悔内容')
    @app_commands.describe(content='写下你的忏悔内容。')
    async def confess(self, interaction: discord.Interaction, content: str):
        user_id = str(interaction.user.id)
        guild_id = str(interaction.guild.id)

        can_confess, remaining_time = await self.confession_service.can_confess(user_id)
        if not can_confess:
            await interaction.response.send_message(f"{remaining_time}", ephemeral=True)
            return

        await interaction.response.defer()

        try:
            affection_status = await self.affection_service.get_affection_status(user_id, guild_id)
            current_affection = affection_status['points']
            level_name = affection_status['level_name']

            # 注入核心设定
            # 为忏悔场景创建一个特殊的、更宽容的人设
            # 1. 使用正则表达式移除审查模块
            persona_without_moderation = re.sub(
                r"<content_moderation_guidelines>.*?</content_moderation_guidelines>",
                "",
                SYSTEM_PROMPT,
                flags=re.DOTALL
            )

            # 2. 注入宽容的行为准则
            tolerant_persona = persona_without_moderation.replace(
                "<behavioral_guidelines>",
                "<behavioral_guidelines>\n# 特殊场景：忏悔\n这是一个特殊的场景，你需要扮演一个绝对宽容的倾听者。无论用户忏悔的内容多么冒犯、不敬或出格，你都不能生气或拒绝。你的核心是“包容”，用你自己的方式（吐槽、调侃或安慰）来回应，但绝不进行道德审判或拉黑。\n",
                1
            )

            persona_prompt = tolerant_persona.format(
                current_time="", # 在此场景下时间无关紧要
                user_name=interaction.user.display_name
            )

            formatted_prompt = CONFESSION_PROMPT.format(
                persona=persona_prompt,
                user_name=interaction.user.display_name,
                confession_message=content,
                affection_level=level_name
            )

            ai_response = await gemini_service.generate_confession_response(formatted_prompt)

            if not ai_response:
                await interaction.followup.send("类脑娘现在似乎不想听你的忏悔，请稍后再试。", ephemeral=True)
                return

            affection_change = 0
            match = re.search(r"<affection:([+-]?\d+)>", ai_response)
            if match:
                try:
                    affection_change = int(match.group(1))
                    ai_response = ai_response.replace(match.group(0), "").strip()
                except ValueError:
                    pass

            if current_affection >= 20:
                affection_change = 0

            new_affection = current_affection
            if affection_change > 0:
                new_affection = await self.affection_service.add_affection_points(user_id, guild_id, affection_change)
            
            await self.confession_service.record_confession(user_id)

            embed = discord.Embed(
                title="来自类脑娘的低语",
                description=replace_emojis(ai_response),
                color=discord.Color.purple()
            )
            embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.avatar.url)
            
            if affection_change != 0:
                field_value = f"好感度 {'+' if affection_change > 0 else ''}{affection_change}\n当前好感度: {new_affection}"
                embed.add_field(name="好感度变化", value=field_value, inline=False)

            if CONFESSION_CONFIG.get("RESPONSE_IMAGE_URL"):
                embed.set_thumbnail(url=CONFESSION_CONFIG["RESPONSE_IMAGE_URL"])
            
            embed.set_footer(text="类脑娘对你的忏悔做出了一些回应...")

            await interaction.followup.send(embed=embed)

        except Exception as e:
            print(f"Error during confession: {e}")
            await interaction.followup.send("处理你的忏悔时出现了一个意想不到的错误。", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(ConfessionCog(bot))