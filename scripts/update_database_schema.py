import sqlite3
import os
import logging
import sys

# 配置日志记录
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 将项目根目录添加到 sys.path
# 这允许我们像在 src 中一样导入模块
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from src import config
except ImportError:
    logging.error("无法导入 src.config。请确保脚本是从项目根目录运行，或者项目结构正确。")
    sys.exit(1)

DB_PATH = os.path.join(config.DATA_DIR, 'world_book.sqlite3')

def table_exists(cursor, table_name):
    """检查表是否已存在"""
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
    return cursor.fetchone() is not None

def column_exists(cursor, table_name, column_name):
    """检查列是否已存在"""
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [row[1] for row in cursor.fetchall()]
    return column_name in columns

def create_pending_entries_table(conn):
    """创建用于存放待审核条目的新表"""
    cursor = conn.cursor()
    if not table_exists(cursor, 'pending_entries'):
        logging.info("正在创建 'pending_entries' 表...")
        cursor.execute("""
            CREATE TABLE pending_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_type TEXT NOT NULL, -- 'community_member' 或 'general_knowledge'
                data_json TEXT NOT NULL, -- 存储原始提交数据的 JSON 字符串
                message_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                proposer_id INTEGER NOT NULL,
                status TEXT DEFAULT 'pending', -- 'pending', 'approved', 'rejected'
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                expires_at DATETIME NOT NULL
            );
        """)
        logging.info("'pending_entries' 表创建成功。")
    else:
        logging.info("'pending_entries' 表已存在，跳过创建。")

def add_status_column(conn, table_name):
    """为指定表添加 status 列"""
    cursor = conn.cursor()
    if not column_exists(cursor, table_name, 'status'):
        logging.info(f"正在为 '{table_name}' 表添加 'status' 列...")
        cursor.execute(f"""
            ALTER TABLE {table_name}
            ADD COLUMN status TEXT DEFAULT 'approved';
        """)
        logging.info(f"'{table_name}' 表的 'status' 列添加成功。")
    else:
        logging.info(f"'{table_name}' 表中已存在 'status' 列，跳过添加。")

def main():
    """主函数，执行数据库架构更新"""
    if not os.path.exists(DB_PATH):
        logging.error(f"数据库文件未找到: {DB_PATH}")
        return

    logging.info(f"正在连接到数据库: {DB_PATH}")
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        
        # 1. 创建 pending_entries 表
        create_pending_entries_table(conn)
        
        # 2. 为 community_members 表添加 status 列
        add_status_column(conn, 'community_members')
        
        # 3. 为 general_knowledge 表添加 status 列
        add_status_column(conn, 'general_knowledge')
        
        conn.commit()
        logging.info("数据库架构更新成功完成。")
        
    except sqlite3.Error as e:
        logging.error(f"数据库操作失败: {e}", exc_info=True)
        if conn:
            conn.rollback()
    except Exception as e:
        logging.error(f"发生未知错误: {e}", exc_info=True)
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()
            logging.info("数据库连接已关闭。")

if __name__ == "__main__":
    main()