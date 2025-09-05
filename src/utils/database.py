import sqlite3
import json
import logging
import os
import asyncio
from functools import partial
from typing import Optional, List, Dict, Any, Callable

# --- 常量定义 ---
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
DB_PATH = os.path.join(_PROJECT_ROOT, "data", "guidance.db")

# --- 日志记录器 ---
log = logging.getLogger(__name__)

class DatabaseManager:
    """管理所有与 SQLite 数据库的异步交互。"""

    def __init__(self, db_path: str = DB_PATH):
        """
        初始化数据库管理器。
        连接将在需要时在执行器中创建。
        """
        self.bot = None
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        # 初始化现在是一个异步方法，需要在 main.py 中显式调用

    async def init_async(self):
        """异步初始化数据库，在事件循环中运行同步的建表逻辑。"""
        log.info("开始异步数据库初始化...")
        await self._execute(self._init_database_logic)
        log.info("异步数据库初始化完成。")

    def set_bot_instance(self, bot):
        """设置 bot 实例以便在数据库模块中使用。"""
        self.bot = bot

    def _init_database_logic(self):
        """
        包含所有同步数据库初始化逻辑的方法。
        这将在一个执行器中运行，以避免阻塞事件循环。
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # --- 服务器配置表 ---
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS guild_configs (
                    guild_id INTEGER PRIMARY KEY,
                    buffer_role_id INTEGER,
                    verified_role_id INTEGER
                );
            """)
            
            # 检查并添加 default_tag_id 列到 guild_configs
            cursor.execute("PRAGMA table_info(guild_configs);")
            columns = [info[1] for info in cursor.fetchall()]
            if 'default_tag_id' not in columns:
                cursor.execute("""
                    ALTER TABLE guild_configs
                    ADD COLUMN default_tag_id INTEGER REFERENCES tags(tag_id) ON DELETE SET NULL;
                """)
                log.info("已向 guild_configs 表添加 default_tag_id 列。")

            # --- 兴趣标签表 ---
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tags (
                    tag_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    tag_name TEXT NOT NULL,
                    description TEXT,
                    UNIQUE(guild_id, tag_name)
                );
            """)
            # --- 引导路径表 ---
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS paths (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tag_id INTEGER NOT NULL,
                    location_id INTEGER NOT NULL,
                    location_type TEXT NOT NULL,
                    message TEXT,
                    step_number INTEGER NOT NULL,
                    deployed_message_id INTEGER,
                    FOREIGN KEY (tag_id) REFERENCES tags(tag_id) ON DELETE CASCADE
                );
            """)
            # --- 引导面板配置表 ---
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS panel_configs (
                    guild_id INTEGER NOT NULL,
                    location_id INTEGER NOT NULL,
                    location_type TEXT NOT NULL,
                    panel_embed_data TEXT,
                    message_id INTEGER,
                    PRIMARY KEY (guild_id, location_id)
                );
            """)
            # --- 触发引导的身份组表 ---
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trigger_roles (
                    guild_id INTEGER NOT NULL,
                    role_id INTEGER NOT NULL,
                    PRIMARY KEY (guild_id, role_id)
                );
            """)
            # --- 消息模板表 ---
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS message_templates (
                    template_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    template_name TEXT NOT NULL,
                    template_data TEXT NOT NULL,
                    UNIQUE(guild_id, template_name)
                );
            """)
            # --- 用户引导进度跟踪表 ---
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_progress (
                    progress_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    guild_id INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    guidance_stage TEXT,
                    selected_tags_json TEXT,
                    generated_path_json TEXT,
                    completed_path_json TEXT,
                    current_step INTEGER,
                    UNIQUE(user_id, guild_id)
                );
            """)
            
            # 检查并添加 remaining_path_json 列到 user_progress
            cursor.execute("PRAGMA table_info(user_progress);")
            columns = [info[1] for info in cursor.fetchall()]
            if 'remaining_path_json' not in columns:
                cursor.execute("""
                    ALTER TABLE user_progress
                    ADD COLUMN remaining_path_json TEXT;
                """)
                log.info("已向 user_progress 表添加 remaining_path_json 列。")

            # --- 已部署面板信息表 ---
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS deployed_panels (
                    guild_id INTEGER PRIMARY KEY,
                    channel_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    last_deployed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            # --- 频道专属消息表 ---
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS channel_messages (
                    channel_id INTEGER PRIMARY KEY,
                    guild_id INTEGER NOT NULL,
                    permanent_message_data TEXT,
                    temporary_message_data TEXT,
                    deployed_message_id INTEGER
                    );
            """)
                
                # --- AI对话上下文表 ---
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ai_conversation_contexts (
                    context_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    guild_id INTEGER NOT NULL,
                    conversation_history TEXT NOT NULL DEFAULT '[]',
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, guild_id)
                    );
            """)
            
            # --- 频道记忆锚点表 ---
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS channel_memory_anchors (
                    guild_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    anchor_message_id INTEGER NOT NULL,
                    PRIMARY KEY (guild_id, channel_id)
                );
            """)
                
                # --- 游戏状态表 ---
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS game_states (
                    game_id TEXT PRIMARY KEY,
                    player_hand TEXT NOT NULL,
                    ai_hand TEXT NOT NULL,
                    ai_strategy TEXT NOT NULL,
                    current_turn TEXT NOT NULL,
                    game_over BOOLEAN NOT NULL DEFAULT 0,
                    winner TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
                
                # --- AI提示词配置表 ---
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ai_prompts (
                    prompt_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    prompt_name TEXT NOT NULL,
                    prompt_content TEXT NOT NULL,
                    is_active BOOLEAN DEFAULT 1,
                    UNIQUE(guild_id, prompt_name)
                );
            """)
                
            # --- 黑名单表 ---
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS blacklisted_users (
                    user_id INTEGER NOT NULL,
                    guild_id INTEGER NOT NULL,
                    expires_at TIMESTAMP NOT NULL,
                    PRIMARY KEY (user_id, guild_id)
                );
            """)
                 
            # --- AI好感度表 ---
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ai_affection (
                    user_id INTEGER NOT NULL,
                    guild_id INTEGER NOT NULL,
                    affection_points INTEGER NOT NULL DEFAULT 0,
                    daily_affection_gain INTEGER NOT NULL DEFAULT 0,
                    last_update_date TEXT,
                    last_interaction_date TEXT,
                    PRIMARY KEY (user_id, guild_id)
                );
            """)

            # 检查并更新 ai_affection 表结构
            cursor.execute("PRAGMA table_info(ai_affection);")
            affection_columns = [info[1] for info in cursor.fetchall()]
            if 'guild_id' not in affection_columns:
                log.info("检测到旧版 ai_affection 表，正在进行结构迁移...")
                # 在一个事务中执行迁移
                try:
                    # 1. 将旧表重命名
                    cursor.execute("ALTER TABLE ai_affection RENAME TO ai_affection_old;")
                    
                    # 2. 创建新结构的新表
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS ai_affection (
                            user_id INTEGER NOT NULL,
                            guild_id INTEGER NOT NULL,
                            affection_points INTEGER NOT NULL DEFAULT 0,
                            daily_affection_gain INTEGER NOT NULL DEFAULT 0,
                            last_update_date TEXT,
                            last_interaction_date TEXT,
                            PRIMARY KEY (user_id, guild_id)
                        );
                    """)
                    
                    # 3. 将旧数据复制到新表 (注意：这里无法填充 guild_id，旧数据将丢失)
                    # 这是一个破坏性更新，但由于没有 guild_id 无法保留旧数据
                    # 如果需要保留，需要一个默认的 guild_id
                    log.warning("ai_affection 表结构迁移：由于缺少 guild_id，旧的好感度数据将无法迁移。")

                    # 4. 删除旧表
                    cursor.execute("DROP TABLE ai_affection_old;")
                    
                    conn.commit()
                    log.info("ai_affection 表结构已成功迁移到新版。")
                except Exception as e:
                    log.error(f"迁移 ai_affection 表结构时出错: {e}", exc_info=True)
                    conn.rollback()
                    raise
            
            # --- 类脑币系统表 ---
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_coins (
                    user_id INTEGER PRIMARY KEY,
                    balance INTEGER NOT NULL DEFAULT 0,
                    last_daily_message_date TEXT
                );
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS shop_items (
                    item_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    description TEXT,
                    price INTEGER NOT NULL,
                    category TEXT NOT NULL,
                    target TEXT NOT NULL DEFAULT 'self',
                    effect_id TEXT,
                    is_available BOOLEAN NOT NULL DEFAULT 1
                );
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_inventory (
                    inventory_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    item_id INTEGER NOT NULL,
                    quantity INTEGER NOT NULL DEFAULT 1,
                    FOREIGN KEY (user_id) REFERENCES user_coins(user_id) ON DELETE CASCADE,
                    FOREIGN KEY (item_id) REFERENCES shop_items(item_id) ON DELETE CASCADE
                );
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS coin_transactions (
                    transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    amount INTEGER NOT NULL,
                    reason TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES user_coins(user_id) ON DELETE CASCADE
                );
            """)
            
            # 检查并添加 coffee_effect_expires_at 列到 user_coins
            cursor.execute("PRAGMA table_info(user_coins);")
            columns = [info[1] for info in cursor.fetchall()]
            if 'coffee_effect_expires_at' not in columns:
                cursor.execute("""
                    ALTER TABLE user_coins
                    ADD COLUMN coffee_effect_expires_at TIMESTAMP;
                """)
                log.info("已向 user_coins 表添加 coffee_effect_expires_at 列。")

            conn.commit()
            log.info(f"数据库表在 {self.db_path} 同步初始化成功。")
        except sqlite3.Error as e:
            log.error(f"同步初始化数据库表时出错: {e}")
            raise
        finally:
            if 'conn' in locals() and conn:
                conn.close()

    async def _execute(self, func: Callable, *args, **kwargs) -> Any:
        """在线程池中执行一个同步的数据库操作。"""
        conn = None
        try:
            # 使用 functools.partial 将函数和参数绑定在一起
            blocking_task = partial(func, *args, **kwargs)
            # 在默认的执行器（线程池）中运行该任务
            result = await asyncio.get_running_loop().run_in_executor(None, blocking_task)
            return result
        except Exception as e:
            log.error(f"数据库执行器出错: {e}", exc_info=True)
            raise

    def _db_transaction(self, query: str, params: tuple = (), *, fetch: str = "none", commit: bool = False):
        """
        一个通用的同步事务函数，用于被 _execute 调用。
        :param query: SQL 查询语句。
        :param params: 查询参数。
        :param fetch: 'one', 'all', or 'none'。
        :param commit: 是否提交事务。
        """
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(query, params)
            
            if fetch == "one":
                result = cursor.fetchone()
            elif fetch == "all":
                result = cursor.fetchall()
            elif fetch == "lastrowid":
                result = cursor.lastrowid
            elif fetch == "rowcount":
                result = cursor.rowcount
            else:
                result = None

            if commit:
                conn.commit()

            return result
        except sqlite3.Error as e:
            if conn:
                conn.rollback()
            log.error(f"数据库事务失败: {e} | Query: {query}")
            raise
        finally:
            if conn:
                conn.close()

    def _db_executemany(self, query: str, params_list: List[tuple]):
        """
        一个同步的 executemany 函数。
        """
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.executemany(query, params_list)
            conn.commit()
            return cursor.rowcount
        except sqlite3.Error as e:
            if conn:
                conn.rollback()
            log.error(f"数据库 executemany 失败: {e} | Query: {query}")
            raise
        finally:
            if conn:
                conn.close()

    async def close(self):
        """关闭数据库连接（在异步模型中通常不需要）。"""
        log.info("数据库管理器正在关闭（异步模式下无操作）。")
        pass

    # --- Guild Configs ---
    async def get_guild_config(self, guild_id: int) -> Optional[sqlite3.Row]:
        query = "SELECT * FROM guild_configs WHERE guild_id = ?"
        return await self._execute(self._db_transaction, query, (guild_id,), fetch="one")

    async def set_stage_role(self, guild_id: int, stage: str, role_id: Optional[int]):
        field_name = f"{stage}_role_id"
        if field_name not in ['buffer_role_id', 'verified_role_id']:
            raise ValueError("无效的阶段名称")
        
        query = f"""
            INSERT INTO guild_configs (guild_id, {field_name})
            VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET
                {field_name} = excluded.{field_name};
        """
        await self._execute(self._db_transaction, query, (guild_id, role_id), commit=True)
        log.info(f"已为服务器 {guild_id} 设置 {stage} 身份组为 {role_id}")

    async def set_default_tag(self, guild_id: int, tag_id: Optional[int]):
        """设置或取消服务器的默认标签。"""
        query = """
            INSERT INTO guild_configs (guild_id, default_tag_id)
            VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET
                default_tag_id = excluded.default_tag_id;
        """
        await self._execute(self._db_transaction, query, (guild_id, tag_id), commit=True)
        log.info(f"已为服务器 {guild_id} 设置默认标签 ID 为 {tag_id}")

    # --- Tags ---
    async def add_tag(self, guild_id: int, name: str, description: Optional[str] = None) -> int:
        query = "INSERT INTO tags (guild_id, tag_name, description) VALUES (?, ?, ?)"
        try:
            lastrowid = await self._execute(self._db_transaction, query, (guild_id, name, description), commit=True, fetch="lastrowid")
            log.info(f"已在服务器 {guild_id} 添加标签: {name}")
            return lastrowid
        except sqlite3.IntegrityError:
            log.warning(f"尝试在服务器 {guild_id} 添加已存在的标签: {name}")
            raise

    async def get_tag_by_id(self, tag_id: int) -> Optional[sqlite3.Row]:
        query = "SELECT * FROM tags WHERE tag_id = ?"
        return await self._execute(self._db_transaction, query, (tag_id,), fetch="one")

    async def get_all_tags(self, guild_id: int) -> List[sqlite3.Row]:
        query = "SELECT * FROM tags WHERE guild_id = ? ORDER BY tag_name"
        return await self._execute(self._db_transaction, query, (guild_id,), fetch="all")

    async def get_tag_by_name(self, guild_id: int, name: str) -> Optional[sqlite3.Row]:
        query = "SELECT * FROM tags WHERE guild_id = ? AND tag_name = ?"
        return await self._execute(self._db_transaction, query, (guild_id, name), fetch="one")

    async def update_tag(self, tag_id: int, name: str, description: Optional[str]) -> int:
        query = "UPDATE tags SET tag_name = ?, description = ? WHERE tag_id = ?"
        try:
            rowcount = await self._execute(self._db_transaction, query, (name, description, tag_id), commit=True, fetch="rowcount")
            if rowcount > 0:
                log.info(f"已更新标签 ID {tag_id} 为: {name}")
            return rowcount
        except sqlite3.IntegrityError:
            log.warning(f"尝试将标签 ID {tag_id} 的名称更新为已存在的名称: {name}")
            raise

    async def delete_tag(self, tag_id: int) -> int:
        query = "DELETE FROM tags WHERE tag_id = ?"
        deleted_rows = await self._execute(self._db_transaction, query, (tag_id,), commit=True, fetch="rowcount")
        if deleted_rows > 0:
            log.info(f"已通过 ID {tag_id} 移除标签。")
        return deleted_rows

    # --- Paths ---
    async def set_path_for_tag(self, tag_id: int, paths_data: List[Dict[str, Any]]):
        # This needs a more complex transaction
        def _transaction():
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            try:
                cursor.execute("DELETE FROM paths WHERE tag_id = ?", (tag_id,))
                steps_to_insert = [
                    (tag_id, path['location_id'], path['location_type'], path.get('message'), i + 1)
                    for i, path in enumerate(paths_data)
                ]
                if steps_to_insert:
                    cursor.executemany(
                        "INSERT INTO paths (tag_id, location_id, location_type, message, step_number) VALUES (?, ?, ?, ?, ?)",
                        steps_to_insert
                    )
                conn.commit()
                log.info(f"已为标签 {tag_id} 设置新路径，包含 {len(paths_data)} 个步骤。")
            except sqlite3.Error as e:
                conn.rollback()
                log.error(f"为标签 {tag_id} 设置路径失败: {e}")
                raise
            finally:
                conn.close()
        await self._execute(_transaction)

    async def get_path_for_tag(self, tag_id: int) -> List[sqlite3.Row]:
        query = "SELECT * FROM paths WHERE tag_id = ? ORDER BY step_number ASC"
        return await self._execute(self._db_transaction, query, (tag_id,), fetch="all")

    async def remove_path_step(self, path_id: int):
        def _transaction():
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            try:
                cursor.execute("SELECT tag_id, step_number FROM paths WHERE id = ?", (path_id,))
                result = cursor.fetchone()
                if not result:
                    return
                
                tag_id, deleted_step_number = result[0], result[1]
                cursor.execute("DELETE FROM paths WHERE id = ?", (path_id,))
                cursor.execute(
                    "UPDATE paths SET step_number = step_number - 1 WHERE tag_id = ? AND step_number > ?",
                    (tag_id, deleted_step_number)
                )
                conn.commit()
                log.info(f"已删除路径步骤 {path_id} 并重新排序。")
            except sqlite3.Error as e:
                conn.rollback()
                log.error(f"删除路径步骤失败 (path_id: {path_id}): {e}")
                raise
            finally:
                conn.close()
        await self._execute(_transaction)

    async def get_configured_path_locations(self, guild_id: int) -> List[sqlite3.Row]:
        """获取一个服务器中所有已配置在引导路径中的唯一地点（频道/帖子）。"""
        query = """
            SELECT DISTINCT p.location_id, p.location_type
            FROM paths p
            INNER JOIN tags t ON p.tag_id = t.tag_id
            WHERE t.guild_id = ?
        """
        return await self._execute(self._db_transaction, query, (guild_id,), fetch="all")

    # --- Trigger Roles ---
    async def get_trigger_roles(self, guild_id: int) -> List[sqlite3.Row]:
        query = "SELECT role_id FROM trigger_roles WHERE guild_id = ?"
        return await self._execute(self._db_transaction, query, (guild_id,), fetch="all")

    async def set_trigger_roles(self, guild_id: int, role_ids: List[int]):
        def _transaction():
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            try:
                cursor.execute("DELETE FROM trigger_roles WHERE guild_id = ?", (guild_id,))
                if role_ids:
                    roles_to_insert = [(guild_id, role_id) for role_id in role_ids]
                    cursor.executemany("INSERT INTO trigger_roles (guild_id, role_id) VALUES (?, ?)", roles_to_insert)
                conn.commit()
                log.info(f"已为服务器 {guild_id} 设置 {len(role_ids)} 个触发身份组。")
            except sqlite3.Error as e:
                conn.rollback()
                log.error(f"设置触发身份组失败 (guild_id: {guild_id}): {e}")
                raise
            finally:
                conn.close()
        await self._execute(_transaction)

    # --- Message Templates ---
    async def get_message_template(self, guild_id: int, template_name: str) -> Optional[Dict[str, Any]]:
        query = "SELECT template_data FROM message_templates WHERE guild_id = ? AND template_name = ?"
        row = await self._execute(self._db_transaction, query, (guild_id, template_name), fetch="one")
        if row:
            try:
                return json.loads(row['template_data'])
            except (json.JSONDecodeError, TypeError):
                log.warning(f"解析服务器 {guild_id} 的模板 {template_name} 时出错。")
        return None

    async def set_message_template(self, guild_id: int, template_name: str, template_data: [Dict[str, Any], List[Dict[str, Any]]]):
        template_json = json.dumps(template_data, ensure_ascii=False)
        query = """
            INSERT INTO message_templates (guild_id, template_name, template_data)
            VALUES (?, ?, ?)
            ON CONFLICT(guild_id, template_name) DO UPDATE SET
                template_data = excluded.template_data;
        """
        await self._execute(self._db_transaction, query, (guild_id, template_name, template_json), commit=True)
        log.info(f"已为服务器 {guild_id} 设置消息模板: {template_name}")

    async def delete_all_message_templates(self, guild_id: int) -> int:
        """删除一个服务器的所有消息模板。"""
        query = "DELETE FROM message_templates WHERE guild_id = ?"
        deleted_rows = await self._execute(self._db_transaction, query, (guild_id,), commit=True, fetch="rowcount")
        if deleted_rows > 0:
            log.info(f"已删除服务器 {guild_id} 的 {deleted_rows} 个消息模板。")
        return deleted_rows

    async def get_all_message_templates(self, guild_id: int) -> Dict[str, Any]:
        query = "SELECT template_name, template_data FROM message_templates WHERE guild_id = ?"
        rows = await self._execute(self._db_transaction, query, (guild_id,), fetch="all")
        templates = {}
        for row in rows:
            try:
                templates[row['template_name']] = json.loads(row['template_data'])
            except (json.JSONDecodeError, TypeError):
                log.warning(f"解析服务器 {guild_id} 的模板 {row['template_name']} 时出错。")
        return templates

    # --- User Progress ---
    async def get_user_progress(self, user_id: int, guild_id: int) -> Optional[sqlite3.Row]:
        query = "SELECT * FROM user_progress WHERE user_id = ? AND guild_id = ?"
        return await self._execute(self._db_transaction, query, (user_id, guild_id), fetch="one")

    async def create_or_reset_user_progress(self, user_id: int, guild_id: int, status: str, guidance_stage: Optional[str] = None) -> sqlite3.Row:
        def _transaction():
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            try:
                cursor.execute("DELETE FROM user_progress WHERE user_id = ? AND guild_id = ?", (user_id, guild_id))
                cursor.execute(
                    "INSERT INTO user_progress (user_id, guild_id, status, guidance_stage, current_step) VALUES (?, ?, ?, ?, ?)",
                    (user_id, guild_id, status, guidance_stage, 1)
                )
                conn.commit()
                cursor.execute("SELECT * FROM user_progress WHERE progress_id = ?", (cursor.lastrowid,))
                log.info(f"已为用户 {user_id} 在服务器 {guild_id} 创建或重置了进度记录，新状态: {status}, 阶段: {guidance_stage}")
                return cursor.fetchone()
            except sqlite3.Error as e:
                conn.rollback()
                log.error(f"创建或重置用户进度失败 (user_id: {user_id}): {e}")
                raise
            finally:
                conn.close()
        return await self._execute(_transaction)

    async def update_user_progress(self, user_id: int, guild_id: int, **kwargs) -> Optional[sqlite3.Row]:
        updates = {key: value for key, value in kwargs.items() if value is not None}
        if not updates:
            return None

        for key, value in updates.items():
            if isinstance(value, (list, dict)):
                updates[key] = json.dumps(value)

        set_clause = ", ".join([f"{key} = ?" for key in updates.keys()])
        values = list(updates.values())
        values.append(user_id)
        values.append(guild_id)

        query = f"UPDATE user_progress SET {set_clause} WHERE user_id = ? AND guild_id = ?"
        await self._execute(self._db_transaction, query, tuple(values), commit=True)
        log.info(f"用户 {user_id} 的进度已更新: {updates}")
        return await self.get_user_progress(user_id, guild_id)

    # --- Deployed Panels ---
    async def log_deployment(self, guild_id: int, channel_id: int, message_id: int):
        query = """
            INSERT INTO deployed_panels (guild_id, channel_id, message_id, last_deployed_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(guild_id) DO UPDATE SET
                channel_id = excluded.channel_id,
                message_id = excluded.message_id,
                last_deployed_at = excluded.last_deployed_at
        """
        await self._execute(self._db_transaction, query, (guild_id, channel_id, message_id), commit=True)
        log.info(f"已记录服务器 {guild_id} 的面板部署信息 (Channel: {channel_id}, Message: {message_id})")

    async def get_deployed_panel(self, guild_id: int) -> Optional[sqlite3.Row]:
        query = "SELECT channel_id, message_id FROM deployed_panels WHERE guild_id = ?"
        return await self._execute(self._db_transaction, query, (guild_id,), fetch="one")

    # --- Channel Messages ---
    async def set_channel_message(self, guild_id: int, channel_id: int, permanent_data: Optional[Dict[str, Any]], temporary_data: Optional[Dict[str, Any]]):
        permanent_json = json.dumps(permanent_data) if permanent_data else None
        temporary_json = json.dumps(temporary_data) if temporary_data else None
        query = """
            INSERT INTO channel_messages (channel_id, guild_id, permanent_message_data, temporary_message_data)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(channel_id) DO UPDATE SET
                guild_id = excluded.guild_id,
                permanent_message_data = excluded.permanent_message_data,
                temporary_message_data = excluded.temporary_message_data
        """
        await self._execute(self._db_transaction, query, (channel_id, guild_id, permanent_json, temporary_json), commit=True)
        log.info(f"已为频道 {channel_id} 设置专属消息。")

    async def get_channel_message(self, channel_id: int) -> Optional[Dict[str, Any]]:
        query = "SELECT * FROM channel_messages WHERE channel_id = ?"
        row = await self._execute(self._db_transaction, query, (channel_id,), fetch="one")
        if not row:
            return None
        
        data = dict(row)
        try:
            if data.get('permanent_message_data'):
                data['permanent_message_data'] = json.loads(data['permanent_message_data'])
            if data.get('temporary_message_data'):
                data['temporary_message_data'] = json.loads(data['temporary_message_data'])
        except (json.JSONDecodeError, TypeError):
            log.warning(f"解析频道 {channel_id} 的专属消息JSON时出错。")
        return data

    def get_channel_message_sync(self, channel_id: int) -> Optional[Dict[str, Any]]:
        """同步版本的 get_channel_message，用于视图内部的快速查找。"""
        row = self._db_transaction("SELECT * FROM channel_messages WHERE channel_id = ?", (channel_id,), fetch="one")
        if not row:
            return None
        
        data = dict(row)
        try:
            if data.get('permanent_message_data'):
                data['permanent_message_data'] = json.loads(data['permanent_message_data'])
            if data.get('temporary_message_data'):
                data['temporary_message_data'] = json.loads(data['temporary_message_data'])
        except (json.JSONDecodeError, TypeError):
            log.warning(f"同步解析频道 {channel_id} 的专属消息JSON时出错。")
        return data

    async def get_all_channel_messages(self, guild_id: int) -> List[Dict[str, Any]]:
        query = "SELECT * FROM channel_messages WHERE guild_id = ?"
        rows = await self._execute(self._db_transaction, query, (guild_id,), fetch="all")
        results = []
        for row in rows:
            data = dict(row)
            try:
                if data.get('permanent_message_data'):
                    data['permanent_message_data'] = json.loads(data['permanent_message_data'])
                if data.get('temporary_message_data'):
                    data['temporary_message_data'] = json.loads(data['temporary_message_data'])
                results.append(data)
            except (json.JSONDecodeError, TypeError):
                log.warning(f"解析频道 {data['channel_id']} 的专属消息JSON时出错。")
        return results

    async def remove_channel_message(self, channel_id: int) -> int:
        query = "DELETE FROM channel_messages WHERE channel_id = ?"
        deleted_rows = await self._execute(self._db_transaction, query, (channel_id,), commit=True, fetch="rowcount")
        if deleted_rows > 0:
            log.info(f"已删除频道 {channel_id} 的专属消息配置。")
        return deleted_rows

    async def update_channel_deployment_id(self, channel_id: int, message_id: Optional[int]):
        query = "UPDATE channel_messages SET deployed_message_id = ? WHERE channel_id = ?"
        await self._execute(self._db_transaction, query, (message_id, channel_id), commit=True)
        log.info(f"已更新频道 {channel_id} 的部署消息ID为 {message_id}。")

    # --- AI对话上下文管理 ---
    async def get_ai_conversation_context(self, user_id: int, guild_id: int) -> Optional[Dict[str, Any]]:
        """获取用户的AI对话上下文"""
        query = "SELECT * FROM ai_conversation_contexts WHERE user_id = ? AND guild_id = ?"
        row = await self._execute(self._db_transaction, query, (user_id, guild_id), fetch="one")
        if row:
            try:
                context = dict(row)
                context['conversation_history'] = json.loads(context['conversation_history'])
                return context
            except (json.JSONDecodeError, TypeError):
                log.warning(f"解析用户 {user_id} 的对话上下文JSON时出错。")
        return None

    async def update_ai_conversation_context(self, user_id: int, guild_id: int, conversation_history: List[Dict]) -> None:
        """更新用户的AI对话上下文"""
        history_json = json.dumps(conversation_history, ensure_ascii=False)
        query = """
            INSERT INTO ai_conversation_contexts (user_id, guild_id, conversation_history)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, guild_id) DO UPDATE SET
                conversation_history = excluded.conversation_history,
                last_updated = CURRENT_TIMESTAMP
        """
        await self._execute(self._db_transaction, query, (user_id, guild_id, history_json), commit=True)

    async def clear_ai_conversation_context(self, user_id: int, guild_id: int) -> None:
        """清除用户的AI对话上下文"""
        query = "DELETE FROM ai_conversation_contexts WHERE user_id = ? AND guild_id = ?"
        await self._execute(self._db_transaction, query, (user_id, guild_id), commit=True)
        log.info(f"已清除用户 {user_id} 在服务器 {guild_id} 的AI对话上下文")

    # --- 频道记忆锚点管理 ---
    async def get_channel_memory_anchor(self, guild_id: int, channel_id: int) -> Optional[int]:
        """获取频道的记忆锚点消息ID"""
        query = "SELECT anchor_message_id FROM channel_memory_anchors WHERE guild_id = ? AND channel_id = ?"
        row = await self._execute(self._db_transaction, query, (guild_id, channel_id), fetch="one")
        return row['anchor_message_id'] if row else None

    async def set_channel_memory_anchor(self, guild_id: int, channel_id: int, anchor_message_id: int) -> None:
        """设置或更新频道的记忆锚点"""
        query = """
            INSERT INTO channel_memory_anchors (guild_id, channel_id, anchor_message_id)
            VALUES (?, ?, ?)
            ON CONFLICT(guild_id, channel_id) DO UPDATE SET
                anchor_message_id = excluded.anchor_message_id;
        """
        await self._execute(self._db_transaction, query, (guild_id, channel_id, anchor_message_id), commit=True)
        log.info(f"已为服务器 {guild_id} 的频道 {channel_id} 设置记忆锚点: {anchor_message_id}")

    async def delete_channel_memory_anchor(self, guild_id: int, channel_id: int) -> int:
        """删除指定频道的记忆锚点"""
        query = "DELETE FROM channel_memory_anchors WHERE guild_id = ? AND channel_id = ?"
        deleted_rows = await self._execute(self._db_transaction, query, (guild_id, channel_id), commit=True, fetch="rowcount")
        if deleted_rows > 0:
            log.info(f"已删除服务器 {guild_id} 频道 {channel_id} 的记忆锚点。")
        return deleted_rows

    # --- AI提示词管理 ---
    async def get_ai_prompt(self, guild_id: int, prompt_name: str) -> Optional[str]:
        """获取AI提示词内容"""
        query = "SELECT prompt_content FROM ai_prompts WHERE guild_id = ? AND prompt_name = ? AND is_active = 1"
        row = await self._execute(self._db_transaction, query, (guild_id, prompt_name), fetch="one")
        return row['prompt_content'] if row else None

    async def set_ai_prompt(self, guild_id: int, prompt_name: str, prompt_content: str) -> None:
        """设置AI提示词"""
        query = """
            INSERT INTO ai_prompts (guild_id, prompt_name, prompt_content)
            VALUES (?, ?, ?)
            ON CONFLICT(guild_id, prompt_name) DO UPDATE SET
                prompt_content = excluded.prompt_content,
                is_active = 1
        """
        await self._execute(self._db_transaction, query, (guild_id, prompt_name, prompt_content), commit=True)
        log.info(f"已为服务器 {guild_id} 设置AI提示词: {prompt_name}")

    async def get_all_ai_prompts(self, guild_id: int) -> Dict[str, str]:
        """获取服务器所有AI提示词"""
        query = "SELECT prompt_name, prompt_content FROM ai_prompts WHERE guild_id = ? AND is_active = 1"
        rows = await self._execute(self._db_transaction, query, (guild_id,), fetch="all")
        return {row['prompt_name']: row['prompt_content'] for row in rows}

    # --- 黑名单管理 ---
    async def add_to_blacklist(self, user_id: int, guild_id: int, expires_at) -> None:
        """将用户添加到黑名单"""
        query = """
            INSERT INTO blacklisted_users (user_id, guild_id, expires_at)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, guild_id) DO UPDATE SET
                expires_at = excluded.expires_at;
        """
        await self._execute(self._db_transaction, query, (user_id, guild_id, expires_at), commit=True)
        log.info(f"已将用户 {user_id} 添加到服务器 {guild_id} 的黑名单，到期时间: {expires_at}")

    async def remove_from_blacklist(self, user_id: int, guild_id: int) -> None:
        """将用户从黑名单中移除"""
        query = "DELETE FROM blacklisted_users WHERE user_id = ? AND guild_id = ?"
        await self._execute(self._db_transaction, query, (user_id, guild_id), commit=True)
        log.info(f"已将用户 {user_id} 从服务器 {guild_id} 的黑名单中移除")

    async def is_user_blacklisted(self, user_id: int, guild_id: int) -> bool:
        """检查用户是否在黑名单中"""
        # 首先清理过期的黑名单记录
        await self._execute(self._db_transaction, "DELETE FROM blacklisted_users WHERE expires_at < datetime('now')", commit=True)
        
        # 然后检查用户是否存在于黑名单中
        query = "SELECT 1 FROM blacklisted_users WHERE user_id = ? AND guild_id = ?"
        result = await self._execute(self._db_transaction, query, (user_id, guild_id), fetch="one")
        return result is not None
    async def get_affection(self, user_id: int, guild_id: int) -> Optional[sqlite3.Row]:
        """获取用户的好感度记录"""
        query = "SELECT * FROM ai_affection WHERE user_id = ? AND guild_id = ?"
        return await self._execute(self._db_transaction, query, (user_id, guild_id), fetch="one")

    async def update_affection(self, user_id: int, guild_id: int, **kwargs) -> None:
        """
        通用更新方法，用于创建或更新用户的好感度记录。
        例如: affection_points=10, daily_affection_gain=5, last_update_date='2023-10-27'
        """
        updates = {key: value for key, value in kwargs.items() if value is not None}
        if not updates:
            return

        # 确保记录存在
        current_affection = await self.get_affection(user_id, guild_id)
        if not current_affection:
            # 如果记录不存在，则插入一条新记录
            insert_query = """
                INSERT INTO ai_affection (user_id, guild_id, affection_points, daily_affection_gain, last_update_date, last_interaction_date)
                VALUES (?, ?, ?, ?, ?, ?)
            """
            # 为所有可能的字段提供默认值
            defaults = {
                'affection_points': 0,
                'daily_affection_gain': 0,
                'last_update_date': None,
                'last_interaction_date': None
            }
            # 使用 kwargs 中的值覆盖默认值
            defaults.update(updates)
            
            await self._execute(self._db_transaction, insert_query, 
                                (user_id, guild_id, defaults['affection_points'], defaults['daily_affection_gain'], 
                                 defaults['last_update_date'], defaults['last_interaction_date']), 
                                commit=True)
            log.info(f"为用户 {user_id} 在服务器 {guild_id} 创建了好感度记录: {defaults}")
            return

        # 如果记录已存在，则更新
        set_clause = ", ".join([f"{key} = ?" for key in updates.keys()])
        values = list(updates.values())
        values.append(user_id)
        values.append(guild_id)

        query = f"UPDATE ai_affection SET {set_clause} WHERE user_id = ? AND guild_id = ?"
        await self._execute(self._db_transaction, query, tuple(values), commit=True)
        log.info(f"用户 {user_id} 在服务器 {guild_id} 的好感度已更新: {updates}")

    async def get_all_affections_for_guild(self, guild_id: int) -> List[sqlite3.Row]:
        """获取一个服务器中所有用户的好感度记录"""
        query = "SELECT * FROM ai_affection WHERE guild_id = ?"
        return await self._execute(self._db_transaction, query, (guild_id,), fetch="all")

    async def reset_daily_affection_gain(self, guild_id: int, new_date: str) -> None:
        """重置服务器内所有用户的每日好感度获得量，并更新日期"""
        query = "UPDATE ai_affection SET daily_affection_gain = 0, last_update_date = ? WHERE guild_id = ?"
        await self._execute(self._db_transaction, query, (new_date, guild_id), commit=True)
        log.info(f"已重置服务器 {guild_id} 的每日好感度获得量，日期更新为 {new_date}")

    async def reset_all_affection_points(self, guild_id: int) -> int:
        """将指定服务器内所有用户的好感度点数重置为0。"""
        query = "UPDATE ai_affection SET affection_points = 0 WHERE guild_id = ?"
        rowcount = await self._execute(self._db_transaction, query, (guild_id,), commit=True, fetch="rowcount")
        log.info(f"已将服务器 {guild_id} 中 {rowcount} 名用户的好感度重置为 0。")
        return rowcount
        

# --- 单例实例 ---
db_manager = DatabaseManager()

if __name__ == '__main__':
    print("这是一个异步数据库模块，不能直接运行。请通过主程序导入和使用。")