import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.types import BotCommand
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.bot.handlers import router


async def main() -> None:
    load_dotenv()

    database_url = os.getenv("DATABASE_URL")
    project_slug = os.getenv("PROJECT_SLUG")

    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured")

    if not project_slug:
        raise RuntimeError("PROJECT_SLUG is not configured")

    engine = create_engine(database_url, pool_pre_ping=True)
    db_sessions = sessionmaker(bind=engine)

    token = os.getenv("BOT_TOKEN")

    if not token:
        raise RuntimeError("BOT_TOKEN is not configured")

    proxy_url = os.getenv("BOT_PROXY_URL")

    session = AiohttpSession(proxy=proxy_url or None)
    bot = Bot(token=token, session=session)

    dispatcher = Dispatcher()
    dispatcher.include_router(router)

    await bot.set_my_commands(
        [
            BotCommand(
                command="start",
                description="Открыть главное меню",
            ),
            BotCommand(
                command="invite",
                description="Управление приглашениями",
            ),
            BotCommand(
                command="invites",
                description="Действующие приглашения",
            ),
        ]
    )

    try:
        await dispatcher.start_polling(
            bot,
            db_sessions=db_sessions,
            project_slug=project_slug,
        )
    finally:
        engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
