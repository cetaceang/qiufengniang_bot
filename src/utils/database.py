import sqlite3
import json
import logging
import os
from typing import Optional, List, Dict, Any

# --- 常量定义 ---
# 从当前文件位置 (src/utils/database.py) 计算出项目根目录的绝对路径
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
DB_PATH = os.path.join(_PROJECT_ROOT, "data", "guidance.db")

# --- 日志记录器 ---
log = logging.getLogger(__name__)

class DatabaseManager:
    """管理所有与 SQLite 数据库的交互。"""

    def __init__(self, db_path: str = DB_PATH):
        """
        初始化数据库连接。
        
        :param db_path: SQLite 数据库文件的路径。
        """
        self.bot = None # 用于存储 bot 实例的引用
        self.db_path = db_path
        try:
            # 确保目录存在
            import os
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
            
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row  # 允许通过列名访问数据
            self.cursor = self.conn.cursor()
            log.info(f"成功连接到数据库: {self.db_path}")
        except sqlite3.Error as e:
            log.error(f"数据库连接失败: {e}")
            raise

    def set_bot_instance(self, bot):
        """设置 bot 实例以便在数据库模块中使用。"""
        self.bot = bot

    def init_database(self):
        """
        如果表不存在，则创建所有必需的表。
        这个函数在每次机器人启动时运行都是安全的。
        """
        try:
            # --- 服务器配置表 (简化) ---
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS guild_configs (
                    guild_id INTEGER PRIMARY KEY
                    -- 未来可在这里添加其他服务器级别的配置
                );
            """)

            # --- 兴趣标签表 ---
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS tags (
                    tag_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    tag_name TEXT NOT NULL,
                    description TEXT,
                    UNIQUE(guild_id, tag_name)
                );
            """)

            # --- 引导路径表 (增加部署消息ID) ---
            self.cursor.execute("""
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

            # --- 引导面板配置表 (兼容频道和帖子) ---
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS panel_configs (
                    guild_id INTEGER NOT NULL,
                    location_id INTEGER NOT NULL,
                    location_type TEXT NOT NULL,
                    panel_embed_data TEXT,
                    message_id INTEGER,
                    PRIMARY KEY (guild_id, location_id)
                );
            """)

            # --- [新] 触发引导的身份组表 ---
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS trigger_roles (
                    guild_id INTEGER NOT NULL,
                    role_id INTEGER NOT NULL,
                    PRIMARY KEY (guild_id, role_id)
                );
            """)

            # --- [新] 消息模板表 ---
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS message_templates (
                    template_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    template_name TEXT NOT NULL,
                    template_data TEXT NOT NULL,
                    UNIQUE(guild_id, template_name)
                );
            """)

            # --- 用户引导进度跟踪表 ---
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_progress (
                    progress_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    guild_id INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    selected_tags_json TEXT,
                    generated_path_json TEXT,
                    current_step INTEGER,
                    UNIQUE(user_id, guild_id)
                );
            """)
            
            # --- [新] 已部署面板信息表 ---
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS deployed_panels (
                    guild_id INTEGER PRIMARY KEY,
                    channel_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    last_deployed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # --- [新] 频道专属消息表 ---
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS channel_messages (
                    channel_id INTEGER PRIMARY KEY,
                    guild_id INTEGER NOT NULL,
                    permanent_message_data TEXT,
                    temporary_message_data TEXT,
                    deployed_message_id INTEGER
                );
            """)
            self.conn.commit()
            log.info("数据库表初始化成功。")
        except sqlite3.Error as e:
            log.error(f"初始化数据库表时出错: {e}")
            self.conn.rollback()
            raise

    def close(self):
        """关闭数据库连接。"""
        if self.conn:
            self.conn.close()
            log.info("数据库连接已关闭。")

    # --- Guild Configs (服务器配置) ---

    def get_guild_config(self, guild_id: int) -> Optional[sqlite3.Row]:
        """获取指定服务器的配置。"""
        try:
            self.cursor.execute("SELECT * FROM guild_configs WHERE guild_id = ?", (guild_id,))
            return self.cursor.fetchone()
        except sqlite3.Error as e:
            log.error(f"获取服务器配置失败 (guild_id: {guild_id}): {e}")
            return None

    def set_guild_config(self, guild_id: int, **kwargs):
        """
        设置或更新服务器的配置项。
        注意：此函数现在主要用于确保服务器在 guild_configs 表中存在记录。
        具体的配置项（如身份组、消息模板）已移至各自的专用表中。
        """
        try:
            self.cursor.execute("INSERT OR IGNORE INTO guild_configs (guild_id) VALUES (?)", (guild_id,))
            
            # 如果有其他需要更新的字段，可以在这里添加逻辑
            # ...

            self.conn.commit()
            log.info(f"确保服务器配置存在 (guild_id: {guild_id})")
        except sqlite3.Error as e:
            log.error(f"更新服务器配置失败 (guild_id: {guild_id}): {e}")
            self.conn.rollback()
            raise

    # --- Panel Configs (引导面板配置) ---

    def get_panel_config(self, location_id: int) -> Optional[sqlite3.Row]:
        """获取指定位置（频道或帖子）的引导面板配置。"""
        try:
            self.cursor.execute("SELECT * FROM panel_configs WHERE location_id = ?", (location_id,))
            return self.cursor.fetchone()
        except sqlite3.Error as e:
            log.error(f"获取面板配置失败 (location_id: {location_id}): {e}")
            return None

    def set_panel_config(self, guild_id: int, location_id: int, location_type: str, panel_data: Dict[str, Any]):
        """设置或更新位置（频道或帖子）的引导面板配置。"""
        try:
            panel_embed_json = json.dumps(panel_data)
            
            # 使用 INSERT OR REPLACE (UPSERT) 逻辑
            self.cursor.execute("""
                INSERT OR REPLACE INTO panel_configs (guild_id, location_id, location_type, panel_embed_data)
                VALUES (?, ?, ?, ?)
            """, (guild_id, location_id, location_type, panel_embed_json))
            
            self.conn.commit()
            log.info(f"成功更新面板配置 (location_id: {location_id}, type: {location_type})")
        except sqlite3.Error as e:
            log.error(f"更新面板配置失败 (location_id: {location_id}): {e}")
            self.conn.rollback()
            raise

    def update_panel_message_id(self, location_id: int, message_id: int):
        """更新指定位置引导面板的消息ID。"""
        try:
            self.cursor.execute(
                "UPDATE panel_configs SET message_id = ? WHERE location_id = ?",
                (message_id, location_id)
            )
            self.conn.commit()
            log.info(f"已更新面板消息ID (location_id: {location_id}, message_id: {message_id})")
        except sqlite3.Error as e:
            log.error(f"更新面板消息ID失败 (location_id: {location_id}): {e}")
            self.conn.rollback()
            raise

    # --- Tags (兴趣标签) ---

    def add_tag(self, guild_id: int, name: str, description: Optional[str] = None) -> sqlite3.Row:
        """向服务器添加一个新标签。"""
        try:
            self.cursor.execute(
                "INSERT INTO tags (guild_id, tag_name, description) VALUES (?, ?, ?)",
                (guild_id, name, description)
            )
            self.conn.commit()
            # 获取刚刚插入的行
            self.cursor.execute("SELECT * FROM tags WHERE tag_id = ?", (self.cursor.lastrowid,))
            log.info(f"已在服务器 {guild_id} 添加标签: {name}")
            return self.cursor.fetchone()
        except sqlite3.IntegrityError:
            # UNIQUE constraint failed
            log.warning(f"尝试在服务器 {guild_id} 添加已存在的标签: {name}")
            raise  # 重新抛出异常，让调用者处理
        except sqlite3.Error as e:
            log.error(f"添加标签失败 (guild_id: {guild_id}, name: {name}): {e}")
            self.conn.rollback()
            raise

    def remove_tag(self, guild_id: int, name: str) -> int:
        """从服务器移除一个标签。返回被删除的行数。"""
        try:
            self.cursor.execute("DELETE FROM tags WHERE guild_id = ? AND tag_name = ?", (guild_id, name))
            self.conn.commit()
            deleted_rows = self.cursor.rowcount
            if deleted_rows > 0:
                log.info(f"已从服务器 {guild_id} 移除标签: {name}")
            return deleted_rows
        except sqlite3.Error as e:
            log.error(f"移除标签失败 (guild_id: {guild_id}, name: {name}): {e}")
            self.conn.rollback()
            raise

    def get_all_tags(self, guild_id: int) -> List[sqlite3.Row]:
        """获取一个服务器的所有标签。"""
        try:
            self.cursor.execute("SELECT * FROM tags WHERE guild_id = ? ORDER BY tag_name", (guild_id,))
            return self.cursor.fetchall()
        except sqlite3.Error as e:
            log.error(f"获取服务器所有标签失败 (guild_id: {guild_id}): {e}")
            return []

    def get_tag_by_name(self, guild_id: int, name: str) -> Optional[sqlite3.Row]:
        """通过名称获取一个标签。"""
        try:
            self.cursor.execute("SELECT * FROM tags WHERE guild_id = ? AND tag_name = ?", (guild_id, name))
            return self.cursor.fetchone()
        except sqlite3.Error as e:
            log.error(f"通过名称获取标签失败 (guild_id: {guild_id}, name: {name}): {e}")
            return None

    def get_tag_by_id(self, tag_id: int) -> Optional[sqlite3.Row]:
        """通过 ID 获取一个标签。"""
        try:
            self.cursor.execute("SELECT * FROM tags WHERE tag_id = ?", (tag_id,))
            return self.cursor.fetchone()
        except sqlite3.Error as e:
            log.error(f"通过 ID 获取标签失败 (tag_id: {tag_id}): {e}")
            return None

    def update_tag(self, tag_id: int, name: str, description: Optional[str]) -> int:
        """通过 ID 更新一个标签的名称和描述。"""
        try:
            self.cursor.execute(
                "UPDATE tags SET tag_name = ?, description = ? WHERE tag_id = ?",
                (name, description, tag_id)
            )
            self.conn.commit()
            updated_rows = self.cursor.rowcount
            if updated_rows > 0:
                log.info(f"已更新标签 ID {tag_id} 为: {name}")
            return updated_rows
        except sqlite3.IntegrityError:
            log.warning(f"尝试将标签 ID {tag_id} 的名称更新为已存在的名称: {name}")
            raise
        except sqlite3.Error as e:
            log.error(f"更新标签失败 (tag_id: {tag_id}): {e}")
            self.conn.rollback()
            raise

    def delete_tag(self, tag_id: int) -> int:
        """通过 ID 从服务器移除一个标签。返回被删除的行数。"""
        try:
            # ON DELETE CASCADE 会处理关联的路径
            self.cursor.execute("DELETE FROM tags WHERE tag_id = ?", (tag_id,))
            self.conn.commit()
            deleted_rows = self.cursor.rowcount
            if deleted_rows > 0:
                log.info(f"已通过 ID {tag_id} 移除标签。")
            return deleted_rows
        except sqlite3.Error as e:
            log.error(f"通过 ID 移除标签失败 (tag_id: {tag_id}): {e}")
            self.conn.rollback()
            raise

    # --- Paths (引导路径) ---

    def set_path_for_tag(self, tag_id: int, paths_data: List[Dict[str, Any]]):
        """
        为一个标签设置一条完整的引导路径。
        :param tag_id: 标签ID。
        :param paths_data: 一个字典列表，每个字典包含 'location_id', 'location_type', 'message'。
        """
        try:
            # 这是一个事务性操作
            # 1. 先清除该标签的旧路径
            self.cursor.execute("DELETE FROM paths WHERE tag_id = ?", (tag_id,))

            # 2. 插入新路径
            steps_to_insert = [
                (tag_id, path['location_id'], path['location_type'], path.get('message'), i + 1)
                for i, path in enumerate(paths_data)
            ]
            if steps_to_insert:
                self.cursor.executemany(
                    "INSERT INTO paths (tag_id, location_id, location_type, message, step_number) VALUES (?, ?, ?, ?, ?)",
                    steps_to_insert
                )
            
            self.conn.commit()
            log.info(f"已为标签 {tag_id} 设置新路径，包含 {len(paths_data)} 个步骤。")
        except sqlite3.Error as e:
            log.error(f"为标签 {tag_id} 设置路径失败: {e}")
            self.conn.rollback()
            raise

    def get_path_for_tag(self, tag_id: int) -> List[sqlite3.Row]:
        """获取一个标签关联的所有路径步骤，按顺序排列。"""
        try:
            self.cursor.execute(
                "SELECT * FROM paths WHERE tag_id = ? ORDER BY step_number ASC",
                (tag_id,)
            )
            return self.cursor.fetchall()
        except sqlite3.Error as e:
            log.error(f"获取标签 {tag_id} 的路径失败: {e}")
            return []

    def clear_path_for_tag(self, tag_id: int) -> int:
        """清除一个标签的所有路径设置。返回被删除的行数。"""
        try:
            self.cursor.execute("DELETE FROM paths WHERE tag_id = ?", (tag_id,))
            self.conn.commit()
            deleted_rows = self.cursor.rowcount
            if deleted_rows > 0:
                log.info(f"已清除标签 {tag_id} 的所有路径。")
            return deleted_rows
        except sqlite3.Error as e:
            log.error(f"清除标签 {tag_id} 的路径失败: {e}")
            self.conn.rollback()
            raise
    def get_configured_path_locations(self, guild_id: int) -> List[sqlite3.Row]:
        """获取一个服务器内，所有在路径中被配置过的唯一地点（频道或帖子）。"""
        try:
            self.cursor.execute("""
                SELECT DISTINCT p.location_id, p.location_type
                FROM paths p
                JOIN tags t ON p.tag_id = t.tag_id
                WHERE t.guild_id = ?
            """, (guild_id,))
            return self.cursor.fetchall()
        except sqlite3.Error as e:
            log.error(f"获取已配置路径地点失败 (guild_id: {guild_id}): {e}")
            return []


    def remove_path_step(self, path_id: int):
        """删除单个路径步骤并重新排序。"""
        try:
            self.conn.execute("BEGIN")
            # 1. 获取被删除步骤的信息
            cursor = self.conn.execute("SELECT tag_id, step_number FROM paths WHERE id = ?", (path_id,))
            result = cursor.fetchone()
            if not result:
                self.conn.rollback()
                return # 步骤不存在

            tag_id, deleted_step_number = result['tag_id'], result['step_number']

            # 2. 删除该步骤
            self.conn.execute("DELETE FROM paths WHERE id = ?", (path_id,))

            # 3. 将所有后续步骤的 step_number 减 1
            self.conn.execute(
                "UPDATE paths SET step_number = step_number - 1 WHERE tag_id = ? AND step_number > ?",
                (tag_id, deleted_step_number)
            )
            
            self.conn.commit()
            log.info(f"已删除路径步骤 {path_id} 并重新排序。")
        except sqlite3.Error as e:
            log.error(f"删除路径步骤失败 (path_id: {path_id}): {e}")
            self.conn.rollback()
            raise

    def get_all_message_templates(self, guild_id: int) -> Dict[str, Any]:
        """获取一个服务器的所有消息模板，以字典形式返回。"""
        try:
            self.cursor.execute(
                "SELECT template_name, template_data FROM message_templates WHERE guild_id = ?",
                (guild_id,)
            )
            rows = self.cursor.fetchall()
            templates = {}
            for row in rows:
                try:
                    templates[row['template_name']] = json.loads(row['template_data'])
                except (json.JSONDecodeError, TypeError):
                    log.warning(f"解析服务器 {guild_id} 的模板 {row['template_name']} 时出错。")
            return templates
        except sqlite3.Error as e:
            log.error(f"获取所有消息模板失败 (guild_id: {guild_id}): {e}")
            return {}

    # --- Deployed Panels (已部署面板) ---

    def log_deployment(self, guild_id: int, channel_id: int, message_id: int):
        """记录或更新已部署的引导面板信息。"""
        try:
            self.cursor.execute("""
                INSERT INTO deployed_panels (guild_id, channel_id, message_id, last_deployed_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(guild_id) DO UPDATE SET
                    channel_id = excluded.channel_id,
                    message_id = excluded.message_id,
                    last_deployed_at = excluded.last_deployed_at
            """, (guild_id, channel_id, message_id))
            self.conn.commit()
            log.info(f"已记录服务器 {guild_id} 的面板部署信息 (Channel: {channel_id}, Message: {message_id})")
        except sqlite3.Error as e:
            log.error(f"记录部署信息失败 (guild_id: {guild_id}): {e}")
            self.conn.rollback()
            raise

    def get_deployed_panel(self, guild_id: int) -> Optional[sqlite3.Row]:
        """获取已部署的引导面板信息。"""
        try:
            self.cursor.execute("SELECT channel_id, message_id FROM deployed_panels WHERE guild_id = ?", (guild_id,))
            return self.cursor.fetchone()
        except sqlite3.Error as e:
            log.error(f"获取已部署面板信息失败 (guild_id: {guild_id}): {e}")
            return None

    # --- Trigger Roles (触发身份组) ---

    def get_trigger_roles(self, guild_id: int) -> List[sqlite3.Row]:
        """获取一个服务器的所有触发身份组。"""
        try:
            self.cursor.execute("SELECT role_id FROM trigger_roles WHERE guild_id = ?", (guild_id,))
            return self.cursor.fetchall()
        except sqlite3.Error as e:
            log.error(f"获取触发身份组失败 (guild_id: {guild_id}): {e}")
            return []

    def set_trigger_roles(self, guild_id: int, role_ids: List[int]):
        """为一个服务器设置完整的触发身份组列表，会覆盖旧列表。"""
        try:
            # 事务性操作
            self.cursor.execute("DELETE FROM trigger_roles WHERE guild_id = ?", (guild_id,))
            if role_ids:
                roles_to_insert = [(guild_id, role_id) for role_id in role_ids]
                self.cursor.executemany("INSERT INTO trigger_roles (guild_id, role_id) VALUES (?, ?)", roles_to_insert)
            self.conn.commit()
            log.info(f"已为服务器 {guild_id} 设置 {len(role_ids)} 个触发身份组。")
        except sqlite3.Error as e:
            log.error(f"设置触发身份组失败 (guild_id: {guild_id}): {e}")
            self.conn.rollback()
            raise

    # --- Message Templates (消息模板) ---

    def get_message_template(self, guild_id: int, template_name: str) -> Optional[sqlite3.Row]:
        """获取指定的消息模板。"""
        try:
            self.cursor.execute(
                "SELECT template_data FROM message_templates WHERE guild_id = ? AND template_name = ?",
                (guild_id, template_name)
            )
            row = self.cursor.fetchone()
            if row:
                # 解析 JSON 数据后返回
                return json.loads(row['template_data'])
            return None
        except (sqlite3.Error, json.JSONDecodeError) as e:
            log.error(f"获取消息模板失败 (guild_id: {guild_id}, name: {template_name}): {e}")
            return None

    def set_message_template(self, guild_id: int, template_name: str, template_data: Dict[str, Any]):
        """创建或更新一个消息模板。"""
        try:
            template_json = json.dumps(template_data)
            self.cursor.execute("""
                INSERT INTO message_templates (guild_id, template_name, template_data)
                VALUES (?, ?, ?)
                ON CONFLICT(guild_id, template_name) DO UPDATE SET
                    template_data = excluded.template_data;
            """, (guild_id, template_name, template_json))
            self.conn.commit()
            log.info(f"已为服务器 {guild_id} 设置消息模板: {template_name}")
        except sqlite3.Error as e:
            log.error(f"设置消息模板失败 (guild_id: {guild_id}, name: {template_name}): {e}")
            self.conn.rollback()
            raise

    # --- User Progress (用户进度) ---

    def get_user_progress(self, user_id: int, guild_id: int) -> Optional[sqlite3.Row]:
        """获取指定用户的引导进度。"""
        try:
            self.cursor.execute("SELECT * FROM user_progress WHERE user_id = ? AND guild_id = ?", (user_id, guild_id))
            return self.cursor.fetchone()
        except sqlite3.Error as e:
            log.error(f"获取用户进度失败 (user_id: {user_id}): {e}")
            return None

    def create_user_progress(self, user_id: int, guild_id: int, status: str) -> sqlite3.Row:
        """为用户创建一条新的进度记录。"""
        try:
            self.cursor.execute(
                "INSERT INTO user_progress (user_id, guild_id, status, current_step) VALUES (?, ?, ?, ?)",
                (user_id, guild_id, status, 1) # 默认从第一步开始
            )
            self.conn.commit()
            self.cursor.execute("SELECT * FROM user_progress WHERE progress_id = ?", (self.cursor.lastrowid,))
            log.info(f"已为用户 {user_id} 在服务器 {guild_id} 创建进度记录，状态: {status}")
            return self.cursor.fetchone()
        except sqlite3.Error as e:
            log.error(f"创建用户进度失败 (user_id: {user_id}): {e}")
            self.conn.rollback()
            raise

    def update_user_progress(self, user_id: int, guild_id: int, **kwargs) -> Optional[sqlite3.Row]:
        """更新用户的进度记录。"""
        updates = {key: value for key, value in kwargs.items() if value is not None}
        if not updates:
            return None

        # 如果更新数据包含列表或字典，将其转换为 JSON 字符串
        for key, value in updates.items():
            if isinstance(value, (list, dict)):
                updates[key] = json.dumps(value)

        try:
            set_clause = ", ".join([f"{key} = ?" for key in updates.keys()])
            values = list(updates.values())
            values.append(user_id)
            values.append(guild_id)

            self.cursor.execute(f"UPDATE user_progress SET {set_clause} WHERE user_id = ? AND guild_id = ?", tuple(values))
            self.conn.commit()
            
            log.info(f"用户 {user_id} 的进度已更新: {updates}")
            return self.get_user_progress(user_id, guild_id)
        except sqlite3.Error as e:
            log.error(f"更新用户进度失败 (user_id: {user_id}): {e}")
            self.conn.rollback()
            raise

    def create_or_reset_user_progress(self, user_id: int, guild_id: int, status: str) -> sqlite3.Row:
        """
        为用户创建或重置进度记录。
        如果记录已存在，则删除旧记录并创建新记录。
        """
        try:
            # 这是一个事务性操作
            # 1. 先尝试删除该用户的旧记录
            self.cursor.execute(
                "DELETE FROM user_progress WHERE user_id = ? AND guild_id = ?",
                (user_id, guild_id)
            )
            
            # 2. 插入新记录
            self.cursor.execute(
                "INSERT INTO user_progress (user_id, guild_id, status, current_step) VALUES (?, ?, ?, ?)",
                (user_id, guild_id, status, 1) # 默认从第一步开始
            )
            self.conn.commit()
            
            self.cursor.execute("SELECT * FROM user_progress WHERE progress_id = ?", (self.cursor.lastrowid,))
            log.info(f"已为用户 {user_id} 在服务器 {guild_id} 创建或重置了进度记录，新状态: {status}")
            return self.cursor.fetchone()
        except sqlite3.Error as e:
            log.error(f"创建或重置用户进度失败 (user_id: {user_id}): {e}")
            self.conn.rollback()
            raise

    # --- Channel Messages (频道专属消息) ---

    def set_channel_message(self, guild_id: int, channel_id: int, permanent_data: Optional[Dict[str, Any]], temporary_data: Optional[Dict[str, Any]]):
        """设置或更新一个频道的专属永久和临时消息。"""
        try:
            permanent_json = json.dumps(permanent_data) if permanent_data else None
            temporary_json = json.dumps(temporary_data) if temporary_data else None
            self.cursor.execute("""
                INSERT INTO channel_messages (channel_id, guild_id, permanent_message_data, temporary_message_data)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(channel_id) DO UPDATE SET
                    guild_id = excluded.guild_id,
                    permanent_message_data = excluded.permanent_message_data,
                    temporary_message_data = excluded.temporary_message_data
            """, (channel_id, guild_id, permanent_json, temporary_json))
            self.conn.commit()
            log.info(f"已为频道 {channel_id} 设置专属消息。")
        except sqlite3.Error as e:
            log.error(f"为频道 {channel_id} 设置专属消息失败: {e}")
            self.conn.rollback()
            raise

    def get_channel_message(self, channel_id: int) -> Optional[Dict[str, Any]]:
        """获取一个频道的专属消息配置。返回一个字典。"""
        try:
            self.cursor.execute("SELECT * FROM channel_messages WHERE channel_id = ?", (channel_id,))
            row = self.cursor.fetchone()
            if not row:
                return None
            
            data = dict(row)
            if data.get('permanent_message_data'):
                data['permanent_message_data'] = json.loads(data['permanent_message_data'])
            if data.get('temporary_message_data'):
                data['temporary_message_data'] = json.loads(data['temporary_message_data'])
            return data
        except (sqlite3.Error, json.JSONDecodeError) as e:
            log.error(f"获取频道 {channel_id} 的专属消息失败: {e}")
            return None

    def get_all_channel_messages(self, guild_id: int) -> List[Dict[str, Any]]:
        """获取一个服务器所有已配置的频道专属消息。"""
        try:
            self.cursor.execute("SELECT * FROM channel_messages WHERE guild_id = ?", (guild_id,))
            rows = self.cursor.fetchall()
            results = []
            for row in rows:
                data = dict(row)
                if data.get('permanent_message_data'):
                    data['permanent_message_data'] = json.loads(data['permanent_message_data'])
                if data.get('temporary_message_data'):
                    data['temporary_message_data'] = json.loads(data['temporary_message_data'])
                results.append(data)
            return results
        except (sqlite3.Error, json.JSONDecodeError) as e:
            log.error(f"获取服务器 {guild_id} 的所有频道专属消息失败: {e}")
            return []

    def remove_channel_message(self, channel_id: int) -> int:
        """删除一个频道的专属消息配置。"""
        try:
            self.cursor.execute("DELETE FROM channel_messages WHERE channel_id = ?", (channel_id,))
            self.conn.commit()
            deleted_rows = self.cursor.rowcount
            if deleted_rows > 0:
                log.info(f"已删除频道 {channel_id} 的专属消息配置。")
            return deleted_rows
        except sqlite3.Error as e:
            log.error(f"删除频道 {channel_id} 的专属消息配置失败: {e}")
            self.conn.rollback()
            raise

    def update_channel_deployment_id(self, channel_id: int, message_id: Optional[int]):
        """更新频道专属消息的部署后消息ID。"""
        try:
            self.cursor.execute(
                "UPDATE channel_messages SET deployed_message_id = ? WHERE channel_id = ?",
                (message_id, channel_id)
            )
            self.conn.commit()
            log.info(f"已更新频道 {channel_id} 的部署消息ID为 {message_id}。")
        except sqlite3.Error as e:
            log.error(f"更新频道 {channel_id} 的部署消息ID失败: {e}")
            self.conn.rollback()
            raise

# --- 单例实例 ---
# 这允许我们在整个项目中导入同一个 db_manager 实例。
# 使用方法: from utils.database import db_manager
db_manager = DatabaseManager()

if __name__ == '__main__':
    # 这允许我们直接运行此脚本来初始化数据库
    print("正在初始化数据库...")
    
    db_manager_for_init = DatabaseManager()
    db_manager_for_init.init_database()
    db_manager_for_init.close()
    print(f"数据库已在 {DB_PATH} 成功初始化。")