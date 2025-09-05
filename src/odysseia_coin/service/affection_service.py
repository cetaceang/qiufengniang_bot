import logging
from src.utils.database import db_manager

log = logging.getLogger(__name__)

class AffectionService:
    """处理用户与AI好感度相关的业务逻辑"""

    async def get_affection(self, user_id: int) -> float:
        """获取用户对AI的好感度"""
        query = "SELECT affection_level FROM ai_affection WHERE user_id = ?"
        result = await db_manager._execute(db_manager._db_transaction, query, (user_id,), fetch="one")
        return result['affection_level'] if result else 0.0

    async def increase_affection(self, user_id: int, amount: float) -> float:
        """
        增加用户对AI的好感度。
        返回新的好感度等级。
        """
        if amount <= 0:
            return await self.get_affection(user_id)

        query = """
            INSERT INTO ai_affection (user_id, affection_level) VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET affection_level = affection_level + excluded.affection_level;
        """
        await db_manager._execute(db_manager._db_transaction, query, (user_id, amount), commit=True)
        
        new_affection_level = await self.get_affection(user_id)
        log.info(f"用户 {user_id} 的好感度增加了 {amount}。新等级: {new_affection_level}")
        return new_affection_level

    async def decrease_affection(self, user_id: int, amount: float) -> float:
        """
        降低用户对AI的好感度。
        返回新的好感度等级。
        """
        if amount <= 0:
            return await self.get_affection(user_id)

        # 好感度最低为0
        current_affection = await self.get_affection(user_id)
        new_affection = max(0, current_affection - amount)

        query = """
            INSERT INTO ai_affection (user_id, affection_level) VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET affection_level = ?;
        """
        await db_manager._execute(db_manager._db_transaction, query, (user_id, new_affection, new_affection), commit=True)
        
        log.info(f"用户 {user_id} 的好感度降低了 {amount}。新等级: {new_affection}")
        return new_affection

# 单例实例
affection_service = AffectionService()