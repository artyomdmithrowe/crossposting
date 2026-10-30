import asyncio
import logging

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import CommandStart
from aiogram.types import Message
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.database.models import Project, User
from app.services.registration import check_access_and_update_profile

router = Router(name="start")
logger = logging.getLogger(__name__)


def get_user_access(
    db_sessions: sessionmaker[Session],
    telegram_id: int,
    username: str | None,
    first_name: str | None,
    project_slug: str,
) -> tuple[str, str | None, bool]:
    with db_sessions.begin() as session:
        role = check_access_and_update_profile(
            session=session,
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            project_slug=project_slug,
        )

        project_name = session.scalar(
            select(Project.name).where(Project.slug == project_slug)
        )
        if project_name is None:
            raise LookupError(f"Unknown project: {project_slug}")

        is_platform_admin = session.scalar(
            select(User.is_platform_admin).where(User.telegram_id == telegram_id)
        )

        return project_name, role, bool(is_platform_admin)


@router.message(
    CommandStart(deep_link=False),
    F.chat.type == ChatType.PRIVATE,
)
async def command_start(
    message: Message,
    db_sessions: sessionmaker[Session],
    project_slug: str,
) -> None:
    user = message.from_user
    if user is None:
        return

    try:
        project_name, role, is_platform_admin = await asyncio.to_thread(
            get_user_access,
            db_sessions,
            user.id,
            user.username,
            user.first_name,
            project_slug,
        )
    except (SQLAlchemyError, LookupError):
        logger.exception("Failed to register user or check access")
        await message.answer("Не удалось проверить права доступа. Попробуйте позже.")
        return

    lines = [
        f"Привет, {user.first_name}!",
        "",
        f"Проект: {project_name}",
    ]

    if is_platform_admin:
        lines.append("🛠 Вы администратор платформы.")

    if role == "owner":
        lines.append("👑 Ваша роль в проекте: владелец.")
    elif role == "editor":
        lines.append("✏️ Ваша роль в проекте: редактор.")
    else:
        lines.append("У вас пока нет прав на публикацию в этом проекте.")

        if not is_platform_admin:
            lines.append(
                f"Ваш Telegram ID: {user.id}\n"
                "Обратитесь к владельцу проекта для получения доступа."
            )

    await message.answer("\n".join(lines))
