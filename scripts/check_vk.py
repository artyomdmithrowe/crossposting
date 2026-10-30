import asyncio
import os

import aiohttp
from dotenv import load_dotenv

from app.integrations.vk.client import VkClient


async def main() -> None:
    load_dotenv()

    token = os.getenv("VK_ACCESS_TOKEN")
    group_id = os.getenv("VK_GROUP_ID")
    api_version = os.getenv("VK_API_VERSION", "5.199")

    if not token:
        raise RuntimeError("VK_ACCESS_TOKEN is not configured")

    if not group_id:
        raise RuntimeError("VK_GROUP_ID is not configured")

    group_id_int = int(group_id)

    if group_id_int <= 0:
        raise ValueError("VK_GROUP_ID must be positive")

    timeout = aiohttp.ClientTimeout(total=15)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        client = VkClient(
            token=token,
            api_version=api_version,
            session=session,
        )

        result = await client.call("groups.getTokenPermissions")

        permissions = {
            permission["name"] for permission in result.get("permissions", [])
        }

    print("✅ Ключ сообщества VK работает!")
    print(f"ID тестового сообщества: {group_id_int}")
    print(f"Разрешения: {', '.join(sorted(permissions))}")

    for required in ("wall", "stories"):
        if required in permissions:
            print(f"✅ Право {required} предоставлено")
        else:
            print(f"⚠️ Право {required} отсутствует")


if __name__ == "__main__":
    asyncio.run(main())
