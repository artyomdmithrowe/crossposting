import asyncio
from collections.abc import Mapping
from typing import Any

import aiohttp


class VkApiError(Exception):
    def __init__(self, code: int | None, message: str) -> None:
        self.code = code
        super().__init__(f"VK API error {code}: {message}")


class VkTransportError(Exception):
    pass


class VkClient:
    BASE_URL = "https://api.vk.com/method"

    def __init__(
        self,
        *,
        token: str,
        api_version: str,
        session: aiohttp.ClientSession,
    ) -> None:
        self._token = token
        self._api_version = api_version
        self._session = session

    async def call(
        self,
        method: str,
        params: Mapping[str, str | int] | None = None,
    ) -> Any:
        data = {key: str(value) for key, value in (params or {}).items()}

        data["access_token"] = self._token
        data["v"] = self._api_version

        try:
            async with self._session.post(
                f"{self.BASE_URL}/{method}",
                data=data,
            ) as response:
                response.raise_for_status()
                payload = await response.json()

        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
            raise VkTransportError("Не удалось получить ответ от VK API.") from exc

        if not isinstance(payload, dict):
            raise VkApiError(None, "Unexpected API response")

        if "error" in payload:
            error = payload["error"]

            raise VkApiError(
                code=error.get("error_code"),
                message=error.get("error_msg", "Unknown error"),
            )

        if "response" not in payload:
            raise VkApiError(None, "Missing response field")

        return payload["response"]
