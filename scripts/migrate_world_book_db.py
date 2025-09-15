import sqlite3
import os
import logging

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger(__name__)

def migrate_database():
    """
    迁移 world_book.sqlite3 数据库，添加缺失的列。
    """
    db_path = os.path.join('data', 'world_book.sqlite3')
    
    if not os.path.exists(db_path):
        log.warning(f"数据库文件 '{db_path}' 不存在。请先运行 initialize_world_book_db.py。")
        return

    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 检查并添加 contributor_id 列
        cursor.execute("PRAGMA table_info(general_knowledge)")
        columns = [col[1] for col in cursor.fetchall()]

        if 'contributor_id' not in columns:
            log.info("在 general_knowledge 表中添加 contributor_id 列...")
            cursor.execute("ALTER TABLE general_knowledge ADD COLUMN contributor_id INTEGER")
            log.info("contributor_id 列添加成功。")
        else:
            log.info("general_knowledge 表已包含 contributor_id 列。")

        # 检查并添加 created_at 列
        if 'created_at' not in columns:
            log.info("在 general_knowledge 表中添加 created_at 列 (不带默认值)...")
            cursor.execute("ALTER TABLE general_knowledge ADD COLUMN created_at TEXT")
            log.info("created_at 列添加成功。")
            
            log.info("为现有的 general_knowledge 条目设置 created_at 默认值...")
            cursor.execute("UPDATE general_knowledge SET created_at = datetime('now') WHERE created_at IS NULL")
            log.info("现有条目的 created_at 默认值设置成功。")
        else:
            log.info("general_knowledge 表已包含 created_at 列。")

        conn.commit()
        log.info("数据库迁移完成。")

    except sqlite3.Error as e:
        log.error(f"数据库迁移失败: {e}", exc_info=True)
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

if __name__ == '__main__':
    migrate_database()