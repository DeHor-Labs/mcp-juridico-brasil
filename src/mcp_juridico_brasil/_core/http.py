"""Cliente HTTP async com retry, rate limiting e cache curto."""

from __future__ import annotations

from typing import Any

import httpx
from aiolimiter import AsyncLimiter
from cachetools import TTLCache
from tenacity import AsyncRetrying, retry_if_exception, stop_after_attempt, wait_exponential

from .logging import get_logger

__all__ = ["HTTPClient"]

logger = get_logger(__name__)

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _RETRYABLE_STATUS
    return isinstance(exc, (httpx.ConnectError, httpx.TimeoutException))


class HTTPClient:
    """Cliente JSON async para servicos externos do MCP Juridico Brasil."""

    def __init__(
        self,
        base_url: str,
        headers: dict[str, str] | None = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        cache_ttl: int = 300,
        rate_limit_per_second: int = 5,
    ) -> None:
        self._base_url = base_url
        self._headers = headers or {}
        self._timeout = timeout
        self._max_retries = max_retries
        self._cache: TTLCache[str, Any] = TTLCache(maxsize=512, ttl=cache_ttl)
        self._limiter = AsyncLimiter(rate_limit_per_second, 1.0)
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> HTTPClient:
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers=self._headers,
            timeout=self._timeout,
        )
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """GET com cache TTL e retry automatico."""
        cache_key = f"GET:{path}:{params}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        result = await self._request("GET", path, params=params)
        self._cache[cache_key] = result
        return result

    async def post(self, path: str, json: dict[str, Any] | None = None) -> Any:
        """POST sem cache (usado para buscas Elasticsearch no DataJud)."""
        return await self._request("POST", path, json=json)

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        if self._client is None:
            raise RuntimeError("HTTPClient nao inicializado. Use como context manager.")

        async with self._limiter:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(self._max_retries),
                wait=wait_exponential(multiplier=0.5, min=0.5, max=10),
                retry=retry_if_exception(_is_retryable),
                reraise=True,
            ):
                with attempt:
                    response = await self._client.request(method, path, **kwargs)
                    response.raise_for_status()
                    logger.debug(
                        "http_request_ok",
                        method=method,
                        path=path,
                        status=response.status_code,
                    )
                    return response.json()
