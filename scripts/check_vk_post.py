import argparse
import asyncio
import os

import aiohttp
from dotenv import load_dotenv

from app.integrations.vk.client import VkClient

TEST_MESSAGE = (
    "🧪 Тестовая публикация Crossposting\n\n"
    "Этот пост опубликован автоматически через VK API.\n\n"
    "Проверяем интеграцию Telegram и ВКонтакте."
)


async def publish_test_post(
    *,
    token: str,
    group_id: int,
    api_version: str,
) -> int:
    timeout = aiohttp.ClientTimeout(total=15)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        client = VkClient(
            token=token,
            api_version=api_version,
            session=session,
        )

        result = await client.call(
            "wall.post",
            {
                "owner_id": -group_id,
                "from_group": 1,
                "message": TEST_MESSAGE,
            },
        )

    post_id = result.get("post_id")

    if not isinstance(post_id, int):
        raise RuntimeError("VK API did not return a valid post_id")

    return post_id


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Опубликовать тестовую запись в VK",
    )

    args = parser.parse_args()

    group_id_raw = os.getenv("VK_GROUP_ID")

    if not group_id_raw:
        raise RuntimeError("VK_GROUP_ID is not configured")

    group_id = int(group_id_raw)

    if group_id <= 0:
        raise ValueError("VK_GROUP_ID must be positive")

    print(f"Тестовое сообщество VK: {group_id}")
    print("\nТекст публикации:\n")
    print(TEST_MESSAGE)

    if not args.publish:
        print("\nℹ️ Предпросмотр. Публикация не выполнялась.")
        print("Для отправки используйте флаг --publish.")
        return

    token = os.getenv("VK_ACCESS_TOKEN")

    if not token:
        raise RuntimeError("VK_ACCESS_TOKEN is not configured")

    post_id = asyncio.run(
        publish_test_post(
            token=token,
            group_id=group_id,
            api_version=os.getenv("VK_API_VERSION", "5.199"),
        )
    )

    print("\n✅ Публикация успешно создана!")
    print(f"https://vk.com/wall-{group_id}_{post_id}")


if __name__ == "__main__":
    main()
