import asyncio
import time
import logging
import random
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Dict, Optional

# 配置日志
log = logging.getLogger(__name__)

class KeyStatus(Enum):
    AVAILABLE = auto()
    IN_USE = auto()
    COOLING_DOWN = auto()
    DISABLED = auto()

@dataclass
class ApiKey:
    key: str
    status: KeyStatus = KeyStatus.AVAILABLE
    last_used: float = 0.0
    cooldown_until: float = 0.0
    reputation: int = 100  # 信誉评分，100为满分
    consecutive_successes: int = 0 # 连续成功次数

class NoAvailableKeyError(Exception):
    """当没有可用Key时抛出此异常"""
    pass

class KeyRotationService:
    """
    管理和轮换API Key的智能服务。
    """
    def __init__(self, api_keys: List[str]):
        if not api_keys:
            raise ValueError("API keys list cannot be empty.")
        
        self.keys: Dict[str, ApiKey] = {key: ApiKey(key=key) for key in api_keys}
        self.lock = asyncio.Lock()
        log.info(f"KeyRotationService initialized with {len(self.keys)} keys.")

    async def acquire_key(self) -> ApiKey:
        """
        获取一个可用的API Key。
        
        会一直等待直到有可用的Key为止。
        """
        while True:
            async with self.lock:
                now = time.time()

                # 步骤 1: 检查冷却时间结束的Key并更新其状态
                for key_obj in self.keys.values():
                    if key_obj.status == KeyStatus.COOLING_DOWN and now >= key_obj.cooldown_until:
                        key_obj.status = KeyStatus.AVAILABLE
                        key_obj.cooldown_until = 0.0
                        log.info(f"Key ...{key_obj.key[-4:]} is now available after cooldown.")

                # 步骤 2: 寻找一个可用的Key
                available_keys = [k for k in self.keys.values() if k.status == KeyStatus.AVAILABLE]

                if available_keys:
                    # 找到最久未使用的Key
                    best_key = min(available_keys, key=lambda k: k.last_used)
                    best_key.status = KeyStatus.IN_USE
                    best_key.last_used = now
                    log.info(f"Acquired key: ...{best_key.key[-4:]}")
                    return best_key

            # 步骤 3: 如果没有可用的Key，等待后重试
            log.debug("No available keys currently, waiting for one to become free.")
            await asyncio.sleep(1)

    async def release_key(self, key: str, success: bool = True):
        """
        释放一个API Key，并根据结果更新其状态。
        
        Args:
            key (str): 要释放的API Key。
            success (bool): 调用是否成功。如果为False，则认为是429错误。
        """
        async with self.lock:
            key_obj = self.keys.get(key)
            if not key_obj:
                log.warning(f"Attempted to release a key that does not exist: {key}")
                return

            if success:
                # 成功调用，将Key状态重置为可用
                key_obj.status = KeyStatus.AVAILABLE
                key_obj.consecutive_successes += 1

                # 计算信誉奖励
                bonus = 0
                if key_obj.consecutive_successes > 0 and key_obj.consecutive_successes % 10 == 0:
                    bonus = 10  # 每连续成功10次，额外奖励10点信誉
                    log.info(f"Key ...{key_obj.key[-4:]} achieved {key_obj.consecutive_successes} consecutive successes. Awarding bonus reputation.")
                
                # 恢复一些信誉，并加上可能的奖励
                key_obj.reputation = min(100, key_obj.reputation + 5 + bonus)
                log.info(f"Key ...{key_obj.key[-4:]} released successfully. Reputation: {key_obj.reputation}. Now available.")
            else:
                # 调用失败 (e.g., 429 error)，进入冷却期
                key_obj.consecutive_successes = 0  # 重置连续成功计数
                key_obj.reputation = max(0, key_obj.reputation - 25)
                cooldown_duration = self._calculate_cooldown(key_obj.reputation)
                key_obj.cooldown_until = time.time() + cooldown_duration
                key_obj.status = KeyStatus.COOLING_DOWN
                log.warning(f"Key ...{key_obj.key[-4:]} failed. Reputation decreased to {key_obj.reputation}. Cooling down for {cooldown_duration:.2f} seconds.")

    def _calculate_cooldown(self, reputation: int) -> float:
        """
        根据信誉评分计算冷却时间。
        """
        if reputation >= 100:
            return 0.0

        # 信誉越低，冷却时间越长。使用指数增长模型。
        # max_cooldown: 当信誉为0时，最长的冷却时间
        # base_cooldown: 基础冷却时间，用于计算
        max_cooldown = 300  # 5 minutes for a key with 0 reputation
        
        # 使用一个非线性公式，信誉越低，惩罚增长越快
        # 当 reputation = 100, penalty_factor = 0
        # 当 reputation = 0, penalty_factor = 1
        penalty_factor = (1 - reputation / 100) ** 2
        
        cooldown = max_cooldown * penalty_factor
        
        # 增加随机抖动，防止所有key同时恢复
        jitter = random.uniform(0, 10)
        
        return cooldown + jitter

    async def disable_key(self, key: str, reason: str):
        """
        永久禁用一个Key（例如，因无效或被吊销）。
        """
        async with self.lock:
            key_obj = self.keys.get(key)
            if key_obj:
                key_obj.status = KeyStatus.DISABLED
                log.error(f"Key ...{key_obj.key[-4:]} has been permanently disabled. Reason: {reason}")
            else:
                log.warning(f"Attempted to disable a key that does not exist: {key}")