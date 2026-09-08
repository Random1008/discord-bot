import redis.asyncio as redis
import redis.exceptions as redis_exceptions

from config.settings import settings


def create_redis_client() -> redis.Redis:
    return redis.from_url(settings.redis_url, decode_responses=True)


async def ping(client: redis.Redis) -> bool:
    try:
        return await client.ping()
    except redis_exceptions.RedisError:
        return False
