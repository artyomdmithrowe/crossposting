import asyncio

import pytest

from app.integrations.vk.client import VkApiError, VkClient


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def raise_for_status(self):
        pass

    async def json(self):
        return self.payload


class FakeSession:
    def __init__(self, payload):
        self.payload = payload
        self.url = None
        self.data = None

    def post(self, url, *, data):
        self.url = url
        self.data = data
        return FakeResponse(self.payload)


def test_vk_client_success():
    session = FakeSession({"response": {"count": 0, "items": []}})

    client = VkClient(
        token="test-token",
        api_version="5.199",
        session=session,
    )

    result = asyncio.run(
        client.call(
            "wall.get",
            {"owner_id": -123456, "count": 1},
        )
    )

    assert result == {"count": 0, "items": []}
    assert session.url == "https://api.vk.com/method/wall.get"
    assert session.data["owner_id"] == "-123456"
    assert session.data["count"] == "1"
    assert session.data["access_token"] == "test-token"
    assert session.data["v"] == "5.199"


def test_vk_client_api_error():
    session = FakeSession(
        {
            "error": {
                "error_code": 5,
                "error_msg": "User authorization failed",
            }
        }
    )

    client = VkClient(
        token="invalid-token",
        api_version="5.199",
        session=session,
    )

    with pytest.raises(VkApiError) as exc_info:
        asyncio.run(client.call("wall.get"))

    assert exc_info.value.code == 5
