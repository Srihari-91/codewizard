"""
Redis-backed rate limiter: max N PRs per hour per repo.
"""

import time
from redis.asyncio import Redis as AsyncRedis
from config import settings


class RateLimiter:
    def __init__(self):
        self._redis = AsyncRedis.from_url(settings.REDIS_URL, decode_responses=True)

    async def check(self, repo_name: str) -> tuple[bool, str]:
        key = f"ratelimit:{repo_name}:{int(time.time()) // 3600}"
        count = await self._redis.incr(key)
        if count == 1:
            await self._redis.expire(key, 3600)
        if count > settings.MAX_PRS_PER_HOUR:
            return False, f"Max {settings.MAX_PRS_PER_HOUR} PRs/hour exceeded"
        return True, "ok"
