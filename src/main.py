# -*- coding: utf-8 -*-

import os
import asyncio
import logging
import sys
import discord
from discord.ext import commands
from dotenv import load_dotenv

# 在所有其他导入之前，尽早加载环境变量
# 这样可以确保所有模块在加载时都能访问到 .env 文件中定义的配置
load_dotenv()

# 从我们自己的模块中导入
from src import config
from src.guidance.utils.database import guidance_db_manager
from src.chat.utils.database import chat_db_manager

def setup_logging():
    """
    配置日志记录器，实现优雅的日志分离：
    - INFO 和 DEBUG 级别的日志输出到 stdout (标准输出)。
    - WARNING, ERROR, CRITICAL 级别的日志输出到 stderr (标准错误)。
    """
    # 1. 创建一个统一的格式化器
    log_formatter = logging.Formatter(config.LOG_FORMAT, datefmt="%Y-%m-%d %H:%M:%S")

    # 2. 创建一个专门处理 INFO 和 DEBUG 级别日志的处理器，并输出到 stdout
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(log_formatter)
    # 添加一个过滤器，只允许低于 WARNING 级别的日志通过
    stdout_handler.addFilter(lambda record: record.levelno < logging.WARNING)

    # 3. 创建一个专门处理 WARNING 及以上级别日志的处理器，并输出到 stderr
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.WARNING)
    stderr_handler.setFormatter(log_formatter)

    # 4. 获取根 logger，并为其添加我们创建的两个处理器
    root_logger = logging.getLogger()
    root_logger.setLevel(config.LOG_LEVEL) # 设置根 logger 的最低响应级别
    root_logger.handlers.clear() # 清除任何可能由其他库（如 discord.py）添加的旧处理器
    root_logger.addHandler(stdout_handler)
    root_logger.addHandler(stderr_handler)

    # 5. 调整特定库的日志级别，以减少不必要的输出
    #    例如，google-generativeai 库在 INFO 级别会打印很多网络请求相关的日志
    #    将所有 google.*, httpx, urllib3 等库的日志级别设为 WARNING，
    #    这样可以屏蔽掉它们所有 INFO 和 DEBUG 级别的冗余日志。
    logging.getLogger("google_genai").setLevel(logging.WARNING)
    logging.getLogger("chromadb").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

class GuidanceBot(commands.Bot):
    """机器人类，继承自 commands.Bot"""
    def __init__(self):
        # 设置机器人需要监听的事件
        intents = discord.Intents.default()
        intents.members = True  # 需要监听成员加入、角色变化
        intents.message_content = True # 根据 discord.py v2.0+ 的要求

        # 解析 GUILD_ID 环境变量，支持用逗号分隔的多个 ID
        debug_guilds = None
        if config.GUILD_ID:
            try:
                # 将环境变量中的字符串转换为整数ID列表
                debug_guilds = [int(gid.strip()) for gid in config.GUILD_ID.split(',')]
                logging.getLogger(__name__).info(f"检测到开发服务器 ID，将以调试模式加载命令到: {debug_guilds}")
            except ValueError:
                logging.getLogger(__name__).error("GUILD_ID 格式错误，请确保是由逗号分隔的纯数字 ID。")
                # 出错时，不使用调试模式，以避免意外行为
                debug_guilds = None

        # 将解析出的列表存储为实例属性，以便在 on_ready 中使用
        self.debug_guild_ids = debug_guilds

        # 使用 debug_guilds 参数初始化机器人
        # 这会将所有斜杠命令自动注册为服务器命令，实现快速更新
        super().__init__(command_prefix="!", intents=intents, debug_guilds=self.debug_guild_ids)

    async def setup_hook(self):
        """
        这是在机器人登录并准备好之后，但在连接到 Discord 之前运行的异步函数。
        我们在这里加载所有的 cogs。
        """
        log = logging.getLogger(__name__)

        # 1. 重新加载持久化视图
        # 这必须在加载 Cogs 之前完成，因为 Cogs 可能依赖于这些视图
        from .guidance.ui.views import GuidancePanelView, PermanentPanelView
        self.add_view(GuidancePanelView())
        log.info("已成功重新加载持久化视图 (GuidancePanelView)。")
        self.add_view(PermanentPanelView())
        log.info("已成功重新加载持久化视图 (PermanentPanelView)。")

        # 2. 加载功能模块 (Cogs)
        log.info("--- 正在加载功能模块 (Cogs) ---")

        # 定义要加载 Cog 的模块路径列表
        cog_module_paths = [
            'src.guidance.cogs',
            'src.chat.cogs'
        ]

        # 动态查找并添加 features 目录下的所有 cogs 模块
        # __file__ 是当前文件 (main.py) 的路径
        # os.path.dirname(__file__) 是 src/ 目录
        features_base_dir = os.path.join(os.path.dirname(__file__), 'chat', 'features')
        if os.path.exists(features_base_dir):
            for feature_name in os.listdir(features_base_dir):
                feature_path = os.path.join(features_base_dir, feature_name)
                if os.path.isdir(feature_path):
                    cogs_path = os.path.join(feature_path, 'cogs')
                    if os.path.exists(cogs_path):
                        cog_module_paths.append(f'src.chat.features.{feature_name}.cogs')

        # 遍历并加载所有找到的 Cog 模块
        for path in cog_module_paths:
            # 将 Python 模块路径转换为文件系统路径
            # 'src.guidance.cogs' -> ['guidance', 'cogs']
            relative_path_parts = path.replace('src.', '').split('.')
            # 'E:\Discord_bot\Odysseia-Guidance\src' + 'guidance' + 'cogs'
            fs_path = os.path.join(os.path.dirname(__file__), *relative_path_parts)
            
            if not os.path.exists(fs_path):
                log.warning(f"Cog 目录不存在: {fs_path}")
                continue

            log.info(f"--- 正在从 {path} 加载 Cogs ---")
            for filename in os.listdir(fs_path):
                if filename.endswith('.py') and not filename.startswith('__'):
                    cog_name = f'{path}.{filename[:-3]}'
                    try:
                        await self.load_extension(cog_name)
                        log.info(f"成功加载模块: {cog_name}")
                    except Exception as e:
                        log.error(f"加载模块 {cog_name} 失败: {e}", exc_info=True)

        log.info("--- 所有模块加载完毕 ---")

    async def on_ready(self):
        """当机器人成功连接到 Discord 时调用"""
        log = logging.getLogger(__name__)
        log.info(f'--- 机器人已上线 ---')
        log.info(f'登录用户: {self.user} (ID: {self.user.id})')
        
        # 同步并列出所有命令，包括子命令
        log.info("--- 机器人已加载的命令 ---")
        for cmd in self.tree.get_commands():
            # 检查是否为命令组
            if isinstance(cmd, discord.app_commands.Group):
                log.info(f"命令组: /{cmd.name}")
                # 遍历并打印组内的所有子命令
                for sub_cmd in cmd.commands:
                    log.info(f"  - /{cmd.name} {sub_cmd.name}")
            else:
                # 如果是单个命令
                log.info(f"命令: /{cmd.name}")
        log.info("--------------------------")

        # 为了在开发时能即时看到命令更新，我们使用一种特殊的同步策略：
        # 如果在 .env 文件中指定了 GUILD_ID，我们将所有命令作为私有命令同步到该服务器，这样可以绕过 Discord 的全局命令缓存。
        # 如果没有指定 GUILD_ID（通常在生产环境中），我们才进行全局同步。
        # 最终的、正确的命令同步逻辑
        # 由于我们使用了 debug_guilds 初始化机器人，discord.py 会自动处理同步目标。
        # 我们只需要调用一次 sync() 即可。
        if self.debug_guild_ids:
            log.info(f"正在将命令同步到开发服务器: {self.debug_guild_ids}...")
        else:
            log.info("未设置开发服务器ID，正在进行全局命令同步（可能需要一小时生效）...")

        try:
            # 如果在初始化时设置了 debug_guilds，sync() 会自动同步到这些服务器。
            # 如果没有设置，sync() 会进行全局同步。
            synced_commands = await self.tree.sync()
            log.info(f"成功同步 {len(synced_commands)} 个命令。")
        except Exception as e:
            log.error(f"同步命令时出错: {e}", exc_info=True)
            
        log.info('--------------------')


async def main():
    """主函数，用于设置和运行机器人"""
    # 1. 配置日志
    setup_logging()
    log = logging.getLogger(__name__)

    # 3. 异步初始化数据库
    log.info("正在异步初始化数据库...")
    await guidance_db_manager.init_async()
    log.info("正在异步初始化 Chat 数据库...")
    await chat_db_manager.init_async()

    # 3.5. 初始化商店商品
    from src.chat.features.odysseia_coin.service.coin_service import coin_service, _setup_initial_items
    await _setup_initial_items()
    log.info("已初始化商店商品。")

    # 4. 创建并运行机器人实例
    bot = GuidanceBot()
    guidance_db_manager.set_bot_instance(bot)
    
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        log.critical("错误: DISCORD_TOKEN 未在 .env 文件中设置！")
        return

    try:
        await bot.start(token)
    except discord.LoginFailure:
        log.critical("无法登录，请检查你的 DISCORD_TOKEN 是否正确。")
    except Exception as e:
        log.critical(f"启动机器人时发生未知错误: {e}", exc_info=True)
    finally:
        # 在机器人关闭时，确保数据库连接被关闭
        await guidance_db_manager.close()
        await chat_db_manager.close()
        log.info("机器人已下线，数据库连接已关闭。")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("通过键盘中断关闭机器人。")
