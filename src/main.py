import os
import asyncio
import logging
import queue
import sys
import discord
import time
import requests
from discord.ext import commands
from dotenv import load_dotenv
from datetime import datetime, timezone

# 在所有其他导入之前，尽早加载环境变量
# 这样可以确保所有模块在加载时都能访问到 .env 文件中定义的配置
load_dotenv()

# 从我们自己的模块中导入
from src import config
from src.guidance.utils.database import guidance_db_manager
from src.chat.utils.database import chat_db_manager
from src.chat.features.world_book.database.world_book_db_manager import world_book_db_manager
# 导入全局 ai_service 实例（支持 Gemini 和 OpenAI 路由）
from src.chat.services.gemini_service import ai_service, gemini_service

current_script_path = os.path.abspath(__file__)
current_dir = os.path.dirname(current_script_path)
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)  

# --- WebUI_start ---
log_server_url = 'http://config_web:80/api/log'
heartbeat_interval = 1.0 #心跳包间隔

log_queue = queue.Queue()
class QueueHandler(logging.Handler):
    def __init__(self,log_queue):
        super().__init__()
        self.log_queue = log_queue
    def emit(self,record):
        self.log_queue.put(self.format(record)) #格式化后入列

def heartbeat_sender():
    while(1):
        time.sleep(heartbeat_interval)
        logs_to_send = []
        while not log_queue.empty():
            try:
                logs_to_send.append(log_queue.get_nowait())
            except queue.Empty:
                break

        try:
            payload = {
            "timestamp":datetime.now(timezone.utc).isoformat(),
            "logs":logs_to_send
            }
            response = requests.post(log_server_url,json=payload,timeout=2.0)
            if response.status_code !=200:
                print(f"Heartbeat Error: Received status {response.status_code}",file=sys.stderr) #不适用logging

        except requests.exceptions.RequestException as e:
            print(f"Heartbeat Error: Could not connet to {log_server_url}.\nDetail:{e}",file=sys.stderr)
# --- WebUI_end ---



if sys.platform != "win32":
    try:
        import uvloop
        uvloop.install()
        logging.info("已成功启用 uvloop 作为 asyncio 事件循环")
    except ImportError:
        logging.warning("尝试启用 uvloop 失败，将使用默认事件循环")

def setup_logging():
    """
    配置日志记录器，实现双通道输出：
    - 控制台 (stdout/stderr): 默认只显示 INFO 及以上级别的日志。
    - 日志文件 (bot_debug.log): 记录 DEBUG 及以上级别的所有日志，用于问题排查。
    """
    # 1. 创建一个统一的格式化器
    log_formatter = logging.Formatter(config.LOG_FORMAT, datefmt="%Y-%m-%d %H:%M:%S")

    # 2. 配置根 logger
    #    为了让文件能记录 DEBUG 信息，根 logger 的级别必须是 DEBUG。
    #    控制台输出的级别将在各自的 handler 中单独控制。
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG) # 设置根 logger 的最低响应级别为 DEBUG
    root_logger.handlers.clear() # 清除任何可能由其他库（如 discord.py）添加的旧处理器

    # 3. 创建控制台处理器 (stdout)，只显示 INFO 和 DEBUG
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(log_formatter)
    # 从 config 文件读取控制台的日志级别
    console_log_level = getattr(logging, config.LOG_LEVEL.upper(), logging.INFO)
    stdout_handler.setLevel(console_log_level)
    # 添加过滤器，确保 WARNING 及以上级别不会在这里输出
    stdout_handler.addFilter(lambda record: record.levelno < logging.WARNING)

    # 4. 创建控制台处理器 (stderr)，只显示 WARNING 及以上
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.WARNING)
    stderr_handler.setFormatter(log_formatter)

    # 5. 创建文件处理器，记录所有 DEBUG 及以上级别的日志
    #    使用 RotatingFileHandler 来自动管理日志文件大小
    from logging.handlers import RotatingFileHandler
    # 确保日志文件所在的目录存在
    log_dir = os.path.dirname(config.LOG_FILE_PATH)
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    file_handler = RotatingFileHandler(
        config.LOG_FILE_PATH,
        maxBytes=5*1024*1024, # 5 MB
        backupCount=2,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG) # 文件记录 DEBUG 级别
    file_handler.setFormatter(log_formatter)

    # --- webui ---
    web_log_formatter = logging.Formatter(
        '[%(asctime)s.%(msecs)03dZ] [%(levelname)s] [%(name)s] %(message)s',
        datefmt='%Y-%m-%dT%H:%M:%S'
    )
    logging.Formatter.converter = time.gmtime

    queue_handler = QueueHandler(log_queue)
    queue_handler.setLevel(logging.DEBUG) #这里如果想在WebUI看到仅INFO以上日志，请在这里修改
    queue_handler.setFormatter(web_log_formatter)

    # 6. 为根 logger 添加所有处理器
    root_logger.addHandler(stdout_handler)
    root_logger.addHandler(stderr_handler)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(queue_handler)

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
        intents.reactions = True # 需要监听反应事件

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

        # 根据是否存在代理和 debug_guilds 来决定初始化参数
        init_kwargs = {
            "command_prefix": "!",
            "intents": intents,
            "debug_guilds": self.debug_guild_ids,
        }
        if config.PROXY_URL:
            init_kwargs["proxy"] = config.PROXY_URL
        
        super().__init__(**init_kwargs)

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
        from pathlib import Path

        # 将 __file__ (当前文件路径) 转换为 Path 对象，并获取其父目录 (src/)
        src_root = Path(__file__).parent

        # 定义所有需要扫描 cogs 的基础路径
        cog_paths_to_scan = [
            src_root / 'guidance' / 'cogs',
            src_root / 'chat' / 'cogs'
        ]

        # 动态查找所有 features/*/cogs 目录并添加到扫描列表
        features_dir = src_root / 'chat' / 'features'
        if features_dir.is_dir():
            for feature in features_dir.iterdir():
                if feature.is_dir():
                    cogs_dir = feature / 'cogs'
                    if cogs_dir.is_dir():
                        cog_paths_to_scan.append(cogs_dir)

        # 遍历所有待扫描的目录，加载其中的 cog
        for path in cog_paths_to_scan:
            # 使用相对于项目根目录的路径进行日志记录，更清晰
            log.info(f"--- 正在从 {path.relative_to(src_root.parent)} 加载 Cogs ---")
            for file in path.glob('*.py'):
                if file.name.startswith('__'):
                    continue

                # 从文件系统路径构建 Python 模块路径
                # 例如: E:\...\src\chat\...\feeding_cog.py -> src.chat....feeding_cog
                relative_path = file.relative_to(src_root.parent)
                module_name = str(relative_path.with_suffix('')).replace(os.path.sep, '.')
                
                try:
                    await self.load_extension(module_name)
                    log.info(f"成功加载模块: {module_name}")
                except Exception as e:
                    log.error(f"加载模块 {module_name} 失败: {e}", exc_info=True)

        log.info("--- 所有模块加载完毕 ---")

    async def on_ready(self):
        """当机器人成功连接到 Discord 时调用"""
        log = logging.getLogger(__name__)
        log.info('--- 机器人已上线 ---')
        if self.user:
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
        # --- 内存诊断代码 ---
        import objgraph
        log.info("--- 开始内存诊断 ---")
        log.info("内存中数量最多的前 20 个对象类型:")
        objgraph.show_most_common_types(limit=20)
        log.info("--- 内存诊断结束 ---")
        log.info("--- 启动成功 ---")


async def main():
    """主函数，用于设置和运行机器人"""
    # 1. 配置日志
    setup_logging()
    log = logging.getLogger(__name__)

    # --- webui心跳启动进程 --
    # log.info("启用webui心跳包")
    # sender_thread = threading.Thread(target=heartbeat_sender,daemon=True)
    # sender_thread.start()
    # log.info("Webui心跳包已启用")

    # 3. 异步初始化数据库
    log.info("正在异步初始化数据库...")
    await guidance_db_manager.init_async()
    log.info("初始化 Chat 数据库...")

    log.info("初始化 World Book 数据库...")
    await world_book_db_manager.init_async()
    await chat_db_manager.init_async()

    # 3.5. 初始化商店商品
    from src.chat.features.odysseia_coin.service.coin_service import _setup_initial_items
    await _setup_initial_items()
    log.info("已初始化商店商品。")

    # 3.6. 导入并注册所有 AI 工具
    # 这是一个关键步骤。通过在这里导入工具模块，我们可以确保
    # @register_tool 装饰器被执行，从而将工具函数及其 Schema
    # 添加到全局的 tool_registry 中。
    from src.chat.features.tools.functions import get_user_avatar
    log.info("已加载并注册 AI 工具。")

    # 4. 创建并运行机器人实例
    bot = GuidanceBot()
    guidance_db_manager.set_bot_instance(bot)
    # 在机器人启动时，将 bot 实例注入到 AI Service 中
    # 这是确保工具能够访问 Discord API 的关键步骤
    ai_service.set_bot(bot)
    
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
