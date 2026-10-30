import asyncio
import logging
from datetime import timezone

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiogram.utils.deep_linking import create_start_link
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.database.models import Project
from app.services.invitations import (
    InvitationError,
    InvitationInfo,
    accept_invitation,
    can_manage_invitations,
    create_invitation,
    list_active_invitations,
    revoke_invitation,
)

router = Router(name="invitations")
logger = logging.getLogger(__name__)


def accept_user_invitation(
    db_sessions: sessionmaker[Session],
    telegram_id: int,
    username: str | None,
    first_name: str | None,
    project_slug: str,
    token: str,
) -> tuple[str, str, bool]:
    with db_sessions.begin() as session:
        result = accept_invitation(
            session,
            project_slug=project_slug,
            token=token,
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
        )

        project_name = session.scalar(
            select(Project.name).where(Project.slug == project_slug)
        )

        if project_name is None:
            raise LookupError(f"Unknown project: {project_slug}")

        return project_name, result.role, result.newly_added


def check_invitation_management(
    db_sessions: sessionmaker[Session],
    project_slug: str,
    telegram_id: int,
) -> bool:
    with db_sessions() as session:
        return can_manage_invitations(
            session,
            project_slug=project_slug,
            user_id=telegram_id,
        )


def create_project_invitation(
    db_sessions: sessionmaker[Session],
    project_slug: str,
    telegram_id: int,
    role: str,
):
    with db_sessions.begin() as session:
        return create_invitation(
            session,
            project_slug=project_slug,
            created_by_id=telegram_id,
            role=role,
        )


def get_project_invitations(
    db_sessions: sessionmaker[Session],
    project_slug: str,
    telegram_id: int,
) -> list[InvitationInfo]:
    with db_sessions() as session:
        return list_active_invitations(
            session,
            project_slug=project_slug,
            requested_by_id=telegram_id,
        )


def revoke_project_invitation(
    db_sessions: sessionmaker[Session],
    project_slug: str,
    telegram_id: int,
    invitation_id: int,
) -> list[InvitationInfo]:
    with db_sessions.begin() as session:
        revoke_invitation(
            session,
            project_slug=project_slug,
            revoked_by_id=telegram_id,
            invitation_id=invitation_id,
        )

        session.flush()

        return list_active_invitations(
            session,
            project_slug=project_slug,
            requested_by_id=telegram_id,
        )


INVITES_PAGE_SIZE = 5


def build_invitations_page(
    invitations: list[InvitationInfo],
    page: int = 0,
) -> tuple[str, InlineKeyboardMarkup | None]:
    if not invitations:
        return (
            "🔗 Действующие приглашения\n\n"
            "Сейчас активных приглашений нет.\n\n"
            "Создать новое можно командой /invite.",
            None,
        )

    total_pages = (len(invitations) + INVITES_PAGE_SIZE - 1) // INVITES_PAGE_SIZE

    page = max(0, min(page, total_pages - 1))

    start = page * INVITES_PAGE_SIZE
    current = invitations[start : start + INVITES_PAGE_SIZE]

    lines = [
        "🔗 Действующие приглашения",
        f"Страница {page + 1} из {total_pages}",
    ]

    buttons = []

    for invitation in current:
        role_name = "👑 Владелец" if invitation.role == "owner" else "✏️ Редактор"

        expires_at = invitation.expires_at.astimezone(timezone.utc).strftime(
            "%d.%m.%Y %H:%M UTC"
        )

        max_uses = "∞" if invitation.max_uses is None else str(invitation.max_uses)

        lines.append(
            f"№{invitation.id} — {role_name}\n"
            f"⏳ До: {expires_at}\n"
            f"🔗 Использований: "
            f"{invitation.uses_count}/{max_uses}"
        )

        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"❌ Отозвать №{invitation.id}",
                    callback_data=(f"inv:revoke:{invitation.id}:{page}"),
                )
            ]
        )

    navigation = []

    if page > 0:
        navigation.append(
            InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data=f"inv:page:{page - 1}",
            )
        )

    if page < total_pages - 1:
        navigation.append(
            InlineKeyboardButton(
                text="Вперёд ➡️",
                callback_data=f"inv:page:{page + 1}",
            )
        )

    if navigation:
        buttons.append(navigation)

    return (
        "\n\n".join(lines),
        InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@router.message(
    CommandStart(deep_link=True),
    F.chat.type == ChatType.PRIVATE,
)
async def command_start_with_invitation(
    message: Message,
    command: CommandObject,
    db_sessions: sessionmaker[Session],
    project_slug: str,
) -> None:
    user = message.from_user

    if user is None:
        return

    payload = command.args

    if payload is None or not payload.startswith("invite_"):
        await message.answer("Некорректная ссылка-приглашение.")
        return

    token = payload[len("invite_") :]

    try:
        project_name, role, newly_added = await asyncio.to_thread(
            accept_user_invitation,
            db_sessions,
            user.id,
            user.username,
            user.first_name,
            project_slug,
            token,
        )

    except InvitationError as exc:
        await message.answer(f"❌ {exc}")
        return

    except (SQLAlchemyError, LookupError):
        logger.exception("Failed to accept project invitation")

        await message.answer("Не удалось обработать приглашение. Попробуйте позже.")
        return

    role_name = "владелец" if role == "owner" else "редактор"

    if newly_added:
        await message.answer(
            "✅ Приглашение принято!\n\n"
            f"Проект: {project_name}\n"
            f"Ваша роль: {role_name}.\n\n"
            "Используйте /start, чтобы открыть главное меню."
        )
    else:
        await message.answer(
            "ℹ️ Вы уже являетесь участником проекта.\n\n"
            f"Проект: {project_name}\n"
            f"Ваша текущая роль: {role_name}.\n\n"
            "Ваши права не изменились."
        )


@router.message(
    Command("invite"),
    F.chat.type == ChatType.PRIVATE,
)
async def command_invite(
    message: Message,
    db_sessions: sessionmaker[Session],
    project_slug: str,
) -> None:
    user = message.from_user

    if user is None:
        return

    try:
        allowed = await asyncio.to_thread(
            check_invitation_management,
            db_sessions,
            project_slug,
            user.id,
        )
    except (SQLAlchemyError, InvitationError):
        logger.exception("Failed to check invitation permissions")

        await message.answer("Не удалось проверить права доступа. Попробуйте позже.")
        return

    if not allowed:
        await message.answer(
            "⛔ Создавать приглашения могут только владельцы "
            "проекта и администраторы платформы."
        )
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✏️ Пригласить редактора",
                    callback_data="inv:create:editor",
                )
            ],
            [
                InlineKeyboardButton(
                    text="👑 Пригласить владельца",
                    callback_data="inv:create:owner",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📋 Действующие приглашения",
                    callback_data="inv:page:0",
                )
            ],
        ]
    )

    await message.answer(
        "🔗 Создание приглашения\n\n"
        "Выберите роль нового участника:\n\n"
        "✏️ Редактор — многоразовая ссылка на 24 часа.\n"
        "👑 Владелец — одноразовая ссылка на 24 часа.",
        reply_markup=keyboard,
    )


@router.callback_query(F.data.in_({"inv:create:owner", "inv:create:editor"}))
async def create_invitation_callback(
    callback: CallbackQuery,
    bot: Bot,
    db_sessions: sessionmaker[Session],
    project_slug: str,
) -> None:
    message = callback.message

    if not isinstance(message, Message) or message.chat.type != ChatType.PRIVATE:
        await callback.answer(
            "Эта команда доступна только в личном чате.",
            show_alert=True,
        )
        return

    role = "owner" if callback.data == "inv:create:owner" else "editor"

    try:
        created = await asyncio.to_thread(
            create_project_invitation,
            db_sessions,
            project_slug,
            callback.from_user.id,
            role,
        )

    except PermissionError:
        await callback.answer(
            "У вас нет прав на создание приглашения.",
            show_alert=True,
        )
        return

    except InvitationError as exc:
        await callback.answer(str(exc), show_alert=True)
        return

    except SQLAlchemyError:
        logger.exception("Failed to create project invitation")

        await callback.answer(
            "Не удалось создать приглашение.",
            show_alert=True,
        )
        return

    await callback.answer("Приглашение создано!")

    link = await create_start_link(
        bot,
        payload=f"invite_{created.token}",
    )

    role_name = "владельца" if role == "owner" else "редактора"

    usage = "Одноразовая" if role == "owner" else "Многоразовая"

    await message.answer(
        f"✅ Ссылка для приглашения {role_name} создана!\n\n"
        f"{link}\n\n"
        f"⏳ Срок действия: 24 часа.\n"
        f"🔗 {usage} ссылка."
    )


@router.message(
    Command("invites"),
    F.chat.type == ChatType.PRIVATE,
)
async def command_invites(
    message: Message,
    db_sessions: sessionmaker[Session],
    project_slug: str,
) -> None:
    user = message.from_user

    if user is None:
        return

    try:
        invitations = await asyncio.to_thread(
            get_project_invitations,
            db_sessions,
            project_slug,
            user.id,
        )

    except PermissionError:
        await message.answer(
            "⛔ Просматривать приглашения могут только "
            "владельцы проекта и администраторы платформы."
        )
        return

    except (InvitationError, SQLAlchemyError, LookupError):
        logger.exception("Failed to list project invitations")

        await message.answer("Не удалось получить приглашения. Попробуйте позже.")
        return

    text, keyboard = build_invitations_page(invitations)

    await message.answer(
        text,
        reply_markup=keyboard,
    )


@router.callback_query(F.data.startswith("inv:page:"))
async def invitations_page_callback(
    callback: CallbackQuery,
    db_sessions: sessionmaker[Session],
    project_slug: str,
) -> None:
    message = callback.message

    if not isinstance(message, Message) or (message.chat.type != ChatType.PRIVATE):
        await callback.answer(
            "Доступно только в личном чате.",
            show_alert=True,
        )
        return

    parts = (callback.data or "").split(":")

    if len(parts) != 3 or not parts[2].isdecimal():
        await callback.answer("Некорректная страница.")
        return

    page = int(parts[2])

    try:
        invitations = await asyncio.to_thread(
            get_project_invitations,
            db_sessions,
            project_slug,
            callback.from_user.id,
        )

    except PermissionError:
        await callback.answer(
            "У вас нет прав на просмотр приглашений.",
            show_alert=True,
        )
        return

    except (InvitationError, SQLAlchemyError, LookupError):
        logger.exception("Failed to paginate invitations")

        await callback.answer(
            "Не удалось получить приглашения.",
            show_alert=True,
        )
        return

    text, keyboard = build_invitations_page(
        invitations,
        page,
    )

    try:
        await message.edit_text(
            text,
            reply_markup=keyboard,
        )
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            logger.exception("Failed to update invitations page")
            await callback.answer(
                "Не удалось обновить список.",
                show_alert=True,
            )
            return

    await callback.answer()


@router.callback_query(F.data.startswith("inv:revoke:"))
async def revoke_invitation_callback(
    callback: CallbackQuery,
    db_sessions: sessionmaker[Session],
    project_slug: str,
) -> None:
    message = callback.message

    if not isinstance(message, Message) or (message.chat.type != ChatType.PRIVATE):
        await callback.answer(
            "Доступно только в личном чате.",
            show_alert=True,
        )
        return

    parts = (callback.data or "").split(":")

    if len(parts) != 4 or not parts[2].isdecimal() or not parts[3].isdecimal():
        await callback.answer(
            "Некорректное приглашение.",
            show_alert=True,
        )
        return

    invitation_id = int(parts[2])
    page = int(parts[3])

    try:
        invitations = await asyncio.to_thread(
            revoke_project_invitation,
            db_sessions,
            project_slug,
            callback.from_user.id,
            invitation_id,
        )

    except PermissionError:
        await callback.answer(
            "У вас нет прав на отзыв приглашений.",
            show_alert=True,
        )
        return

    except InvitationError as exc:
        await callback.answer(
            str(exc),
            show_alert=True,
        )
        return

    except (SQLAlchemyError, LookupError):
        logger.exception("Failed to revoke invitation")

        await callback.answer(
            "Не удалось отозвать приглашение.",
            show_alert=True,
        )
        return

    text, keyboard = build_invitations_page(
        invitations,
        page,
    )

    try:
        await message.edit_text(
            text,
            reply_markup=keyboard,
        )

    except TelegramBadRequest:
        logger.exception("Failed to refresh revoked invitations")

        await callback.answer(
            "Приглашение отозвано, но список не обновился. Используйте /invites.",
            show_alert=True,
        )
        return

    await callback.answer("Приглашение отозвано!")
