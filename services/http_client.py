"""Общий пул HTTP-соединений для внешних API."""
import aiohttp

_session: aiohttp.ClientSession | None = None


async def get_session() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=60),
            connector=aiohttp.TCPConnector(limit=20, ttl_dns_cache=300),
        )
    return _session


async def close_session() -> None:
    global _session
    if _session and not _session.closed:
        await _session.close()
        _session = None
