import fakeredis.aioredis
import redis.asyncio
import redis.exceptions

from utils.redis_client import create_redis_client, ping


async def test_ping_returns_true_for_healthy_client():
    client = fakeredis.aioredis.FakeRedis()

    assert await ping(client) is True

    await client.aclose()


class _FailingClient:
    async def ping(self):
        raise redis.exceptions.ConnectionError("connection refused")


async def test_ping_returns_false_when_redis_unreachable():
    client = _FailingClient()

    assert await ping(client) is False


def test_create_redis_client_returns_async_client():
    client = create_redis_client()

    assert isinstance(client, redis.asyncio.Redis)
