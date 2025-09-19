import aiosqlite
from datetime import datetime, timedelta
from src.chat.utils.database import chat_db_manager

class FeedingService:
    def __init__(self):
        self.db_manager = chat_db_manager

    async def record_feeding(self, user_id: str):
        """记录一次投喂事件"""
        query = "INSERT INTO feeding_log (user_id, timestamp) VALUES (?, ?)"
        await self.db_manager._execute(
            self.db_manager._db_transaction,
            query,
            (user_id, datetime.utcnow().isoformat()),
            commit=True
        )

    async def can_feed(self, user_id: str) -> (bool, str):
        """
        检查用户是否可以投喂。
        返回一个元组 (can_feed: bool, message: str)
        """
        # 1. 检查最近一次投喂时间（冷却时间）
        query1 = "SELECT timestamp FROM feeding_log WHERE user_id = ? ORDER BY timestamp DESC LIMIT 1"
        last_feeding_row = await self.db_manager._execute(
            self.db_manager._db_transaction, query1, (user_id,), fetch="one"
        )

        now = datetime.utcnow()
        if last_feeding_row:
            last_feeding_time = datetime.fromisoformat(last_feeding_row[0])
            time_since_last_feeding = now - last_feeding_time
            if time_since_last_feeding < timedelta(hours=3):
                remaining_time = timedelta(hours=3) - time_since_last_feeding
                hours, remainder = divmod(remaining_time.seconds, 3600)
                minutes, _ = divmod(remainder, 60)
                
                if hours > 0:
                    cooldown_message = f"{hours}小时{minutes}分钟"
                else:
                    cooldown_message = f"{minutes}分钟"
                return False, f"饱啦饱啦, **{cooldown_message}** 后再来吧！"

        # 2. 检查过去24小时内的投喂次数
        one_day_ago = now - timedelta(days=1)
        query2 = "SELECT COUNT(*) FROM feeding_log WHERE user_id = ? AND timestamp >= ?"
        count_row = await self.db_manager._execute(
            self.db_manager._db_transaction, query2, (user_id, one_day_ago.isoformat()), fetch="one"
        )

        feedings_in_last_24_hours = count_row[0] if count_row else 0

        if feedings_in_last_24_hours >= 3:
            return False, "你今天已经给我吃三次啦,肚子饱饱的,明天再说吧！"

        return True, ""

feeding_service = FeedingService()