import discord
from discord.ui import Modal, TextInput

class ExtraConfigModal(Modal, title="设置附加信息"):
    """一个用于输入图片URL和页脚文本的模态框。"""
    def __init__(self, current_image_url: str = "", current_footer: str = ""):
        super().__init__(timeout=300)
        self.submitted_data = None

        # 图片URL输入框
        self.image_url_input = TextInput(
            label="图片 URL (可选)",
            placeholder="在此粘贴图片的直接链接 (https://.../image.png)。留空则为删除。",
            default=current_image_url,
            required=False,
            style=discord.TextStyle.paragraph # 使用长文本样式
        )
        self.add_item(self.image_url_input)

        # 页脚文本输入框
        self.footer_input = TextInput(
            label="页脚文本 (可选)",
            placeholder="在此输入您想在消息底部显示的文本。",
            default=current_footer,
            required=False,
            max_length=2048,
            style=discord.TextStyle.paragraph
        )
        self.add_item(self.footer_input)

    async def on_submit(self, interaction: discord.Interaction):
        """当用户提交模态框时被调用。"""
        url = self.image_url_input.value.strip()
        footer = self.footer_input.value.strip()

        # 自动清理Discord CDN链接中的临时参数
        if url and "cdn.discordapp.com" in url:
            url = url.split('?')[0]

        # URL格式验证
        if url:
            error_message = None
            if not (url.startswith('http://') or url.startswith('https://')):
                error_message = "❌ **图片链接无效**：请输入一个有效的 URL，必须以 `http://` 或 `https://` 开头。"
            elif "discord.com/channels/" in url:
                error_message = (
                    "❌ **图片链接类型错误！**\n\n"
                    "您似乎粘贴了**消息链接**，而不是**图片链接**。\n\n"
                    "**请按以下方式获取正确的图片链接：**\n"
                    "• **电脑端**：右键点击图片，选择“**复制图片链接**”。\n"
                    "• **手机端**：点开图片后长按，选择“**复制图片链接**”。"
                )
            
            if error_message:
                await interaction.response.send_message(error_message, ephemeral=True)
                self.submitted_data = None # 标记为无效提交
                return

        self.submitted_data = {
            "image_url": url or None,
            "footer": footer or None
        }
        
        # 仅响应交互，不做任何回复，让调用者处理后续逻辑
        await interaction.response.defer()