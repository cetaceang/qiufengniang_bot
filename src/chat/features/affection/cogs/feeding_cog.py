import discord
import json
import io
from discord import app_commands
from discord.ext import commands

from src.chat.features.affection.service.affection_service import AffectionService
from src.chat.features.affection.service.feeding_service import feeding_service
from src.chat.features.odysseia_coin.service.coin_service import CoinService
from src.chat.services.gemini_service import gemini_service
from src.chat.config.prompts import SYSTEM_PROMPT
from src.chat.config.chat_config import FEEDING_CONFIG
from src.chat.utils.prompt_utils import extract_persona_prompt, replace_emojis
from src.config import DEVELOPER_USER_IDS
import logging

logger = logging.getLogger(__name__)

class FeedingCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.affection_service = AffectionService()
        self.coin_service = CoinService()
        self.gemini_service = gemini_service # 使用全局实例
        self.feeding_service = feeding_service

    @app_commands.command(name="投喂", description="在吃饭?给类脑娘来一口怎么样")
    @app_commands.describe(image="拍一下你这顿饭是什么吧!")
    async def feed(self, interaction: discord.Interaction, image: discord.Attachment):
        user_id = str(interaction.user.id)
        guild_id = str(interaction.guild.id)

        # 检查用户是否为开发者，如果是，则绕过冷却时间检查
        if interaction.user.id not in DEVELOPER_USER_IDS:
            # 使用 FeedingService 检查是否可以投喂
            can_feed, message = await self.feeding_service.can_feed(user_id)
            if not can_feed:
                await interaction.response.send_message(message, ephemeral=False)
                return

        await interaction.response.defer(ephemeral=False)
        
        if not image.content_type.startswith('image/'):
            await interaction.followup.send("欸？这个不能吃啦，给我看看真正的食物图片嘛！")
            return

        try:
            image_bytes = await image.read()
            
            # 构建包含类脑娘人设的提示词
            persona_part = extract_persona_prompt(SYSTEM_PROMPT)
            prompt = f"{persona_part}\n\n现在，请你对这张图片中的食物进行打分（1-10分），并给出一个简短的、符合你人设的评价。评价中可以包含你对食物的喜好、吐槽或俏皮话，并直接包含分数。\n在评价文本的最后，请严格按照以下格式附加上好感度和类脑币奖励，不要添加任何额外说明：<affection:好感度奖励;coins:类脑币奖励>\n例如：\n这个看起来好好吃！我给10分！<affection:+5;coins:+50>"
            
            response_text = await self.gemini_service.generate_text_with_image(
                prompt=prompt,
                image_bytes=image_bytes,
                mime_type=image.content_type
            )

            if not response_text:
                await interaction.followup.send("抱歉，我有点累了，暂时无法评价呢。")
                return

            # 使用正则表达式解析返回的文本
            import re
            pattern = re.compile(r"(.*?)<affection:([+-]?\d+);coins:([+-]?\d+)>", re.DOTALL)
            match = pattern.search(response_text)

            if not match:
                logger.error(f"解析投喂评价失败。原始文本: '{response_text}'")
                # 如果解析失败，直接将 AI 的回复作为评价，并给予默认奖励
                evaluation = response_text
                affection_gain = 1
                coin_gain = 10
            else:
                evaluation = match.group(1).strip()
                affection_gain = int(match.group(2))
                coin_gain = int(match.group(3))

            await self.affection_service.add_affection_points(user_id, guild_id, affection_gain)

            # 只有当 coin_gain 是正数时才增加类脑币
            if coin_gain > 0:
                await self.coin_service.add_coins(user_id, coin_gain, reason="投喂奖励")

            # 替换表情并添加奖励消息
            evaluation_with_emojis = replace_emojis(evaluation)
            
            # 格式化系统提示，仅在获得奖励时显示
            system_message = ""
            if coin_gain > 0:
                system_message = f"> 你获得了 {coin_gain} 枚类脑币！"
            
            # 创建 Embed
            embed_description = evaluation_with_emojis
            if system_message:
                embed_description += f"\n\n{system_message}"
            
            embed = discord.Embed(
                description=embed_description,
                color=discord.Color.pink()  # 你可以自定义颜色
            )
            
            # 设置作者信息
            embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)

            # 从配置中获取图片 URL
            image_url = FEEDING_CONFIG.get("RESPONSE_IMAGE_URL")
            if image_url:
                embed.set_image(url=image_url)

            # 将用户上传的图片作为缩略图
            file = discord.File(fp=io.BytesIO(image_bytes), filename=image.filename)
            embed.set_thumbnail(url=f"attachment://{image.filename}")

            # 添加页脚用于上下文识别
            embed.set_footer(text="类脑娘对你的投喂做出回应...")

            # 记录投喂事件
            await self.feeding_service.record_feeding(user_id)

            await interaction.followup.send(embed=embed, file=file)

        except json.JSONDecodeError:
            logger.error(f"Failed to decode JSON response from Gemini: {response_text}")
            await interaction.followup.send("呜... 我、我有点尝不出来味道... 你能等一下再喂我吗？")
        except Exception as e:
            logger.error(f"Error processing feeding command: {e}")
            await interaction.followup.send("啊呀，不小心噎着了！等、等我一下，稍后再试试看！")

async def setup(bot: commands.Bot):
    await bot.add_cog(FeedingCog(bot))