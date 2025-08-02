# -*- coding: utf-8 -*-

import os
import asyncio
import logging
import sys
import discord
from discord.ext import commands
from dotenv import load_dotenv

# 从我们自己的模块中导入
from . import config
from .utils.database import db_manager

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
    # 注意：我们不再使用 logging.basicConfig()，因为它会添加自己的默认处理器
    root_logger = logging.getLogger()
    root_logger.setLevel(config.LOG_LEVEL) # 设置根 logger 的最低响应级别
    root_logger.handlers.clear() # 清除任何可能由其他库（如 discord.py）添加的旧处理器
    root_logger.addHandler(stdout_handler)
    root_logger.addHandler(stderr_handler)

class GuidanceBot(commands.Bot):
    """机器人类，继承自 commands.Bot"""
    def __init__(self):
        # 设置机器人需要监听的事件
        intents = discord.Intents.default()
        intents.members = True  # 需要监听成员加入、角色变化
        intents.message_content = True # 根据 discord.py v2.0+ 的要求

        super().__init__(command_prefix="!", intents=intents) # 命令前缀可以随意设置，因为我们主要用斜杠命令

    async def setup_hook(self):
        """
        这是在机器人登录并准备好之后，但在连接到 Discord 之前运行的异步函数。
        我们在这里加载所有的 cogs。
        """
        log = logging.getLogger(__name__)

        # 1. 重新加载持久化视图
        # 这必须在加载 Cogs 之前完成，因为 Cogs 可能依赖于这些视图
        from .utils.views import GuidancePanelView, PermanentPanelView
        self.add_view(GuidancePanelView())
        log.info("已成功重新加载持久化视图 (GuidancePanelView)。")
        self.add_view(PermanentPanelView())
        log.info("已成功重新加载持久化视图 (PermanentPanelView)。")

        # 2. 加载功能模块 (Cogs)
        log.info("--- 正在加载功能模块 (Cogs) ---")
        
        # 确保 cogs 目录存在
        cogs_dir = os.path.join(os.path.dirname(__file__), 'cogs')

        # 确保 cogs 目录存在
        if not os.path.exists(cogs_dir):
            os.makedirs(cogs_dir)
            log.warning("Cogs 目录不存在，已自动创建。")

        for filename in os.listdir(cogs_dir):
            if filename.endswith('.py') and not filename.startswith('__'):
                # load_extension 使用点号分隔的 Python 模块路径
                # load_extension 需要一个完整的、从项目根目录开始的 Python 模块路径。
                # 因为我们使用 `python -m src.main` 启动，所以根包是 `src`。
                cog_name = f'src.cogs.{filename[:-3]}'
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
        if config.GUILD_ID:
            # 开发模式：使用 copy_global_to 实现快速同步，并执行一次性全局清理
            guild = discord.Object(id=int(config.GUILD_ID))
            try:
                # 1. 将所有全局命令定义复制到开发服务器，准备进行覆盖式同步（快速）
                log.info(f"检测到开发服务器 ID: {config.GUILD_ID}。正在准备快速同步...")
                self.tree.copy_global_to(guild=guild)
                
                # 2. 同步开发服务器的命令
                # 这会清除该服务器上所有不由当前机器人代码定义的旧命令，并注册新命令。
                synced_commands = await self.tree.sync(guild=guild)
                log.info(f"已成功同步 {len(synced_commands)} 个命令到开发服务器 {config.GUILD_ID}。")

                # 3. 执行一次性全局命令清理，彻底移除旧的、缓存的全局命令
                log.info("正在执行一次性全局命令清理...")
                self.tree.clear_commands(guild=None)
                await self.tree.sync(guild=None)
                log.info("全局命令清理完成。所有旧命令应已彻底移除。")

            except Exception as e:
                log.error(f"为开发服务器同步命令时出错: {e}", exc_info=True)
        else:
            # 生产模式：只进行标准的全局同步
            log.warning("未设置 GUILD_ID，将进行全局命令同步（可能需要一小时生效）。")
            try:
                await self.tree.sync()
                log.info("全局命令同步完成。")
            except Exception as e:
                log.error(f"全局同步命令时出错: {e}", exc_info=True)
            
        log.info('--------------------')


async def main():
    """主函数，用于设置和运行机器人"""
    # 1. 加载 .env 文件中的环境变量
    load_dotenv()

    # 2. 配置日志
    setup_logging()
    log = logging.getLogger(__name__)

    # 3. 初始化数据库
    log.info("正在初始化数据库...")
    db_manager.init_database()
    log.info("数据库初始化完成。")

    # 4. 创建并运行机器人实例
    bot = GuidanceBot()
    db_manager.set_bot_instance(bot)
    
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
        db_manager.close()
        log.info("机器人已下线，数据库连接已关闭。")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("通过键盘中断关闭机器人。")
