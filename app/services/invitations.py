import hashlib
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.database.models import (
    Project,
    ProjectInvitation,
    ProjectMember,
    User,
)

INVITATION_LIFETIME = timedelta(hours=24)


class InvitationError(Exception):
    pass


@dataclass(frozen=True)
class CreatedInvitation:
    id: int
    token: str
    expires_at: datetime


@dataclass(frozen=True)
class InvitationAcceptance:
    role: str
    newly_added: bool


@dataclass(frozen=True)
class InvitationInfo:
    id: int
    role: str
    created_by_id: int
    expires_at: datetime
    uses_count: int
    max_uses: int | None


def _get_project(session: Session, project_slug: str) -> Project:
    project = session.scalar(select(Project).where(Project.slug == project_slug))

    if project is None:
        raise InvitationError("Проект не найден.")

    return project


def _check_manage_permission(
    session: Session,
    user_id: int,
    project_id: int,
) -> None:
    user = session.get(User, user_id)

    if user is None:
        raise PermissionError("Недостаточно прав.")

    if user.is_platform_admin:
        return

    membership = session.get(
        ProjectMember,
        (project_id, user_id),
    )

    if membership is None or membership.role != "owner":
        raise PermissionError("Недостаточно прав.")


def can_manage_invitations(
    session: Session,
    *,
    project_slug: str,
    user_id: int,
) -> bool:
    project = _get_project(session, project_slug)

    try:
        _check_manage_permission(
            session,
            user_id,
            project.id,
        )
    except PermissionError:
        return False

    return True


def create_invitation(
    session: Session,
    *,
    project_slug: str,
    created_by_id: int,
    role: str,
) -> CreatedInvitation:
    if role not in {"owner", "editor"}:
        raise InvitationError("Недопустимая роль.")

    project = _get_project(session, project_slug)

    _check_manage_permission(
        session,
        created_by_id,
        project.id,
    )

    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    expires_at = datetime.now(timezone.utc) + INVITATION_LIFETIME

    invitation = ProjectInvitation(
        project_id=project.id,
        created_by_id=created_by_id,
        role=role,
        token_hash=token_hash,
        expires_at=expires_at,
        max_uses=1 if role == "owner" else None,
        uses_count=0,
    )

    session.add(invitation)
    session.flush()

    return CreatedInvitation(
        id=invitation.id,
        token=token,
        expires_at=expires_at,
    )


def accept_invitation(
    session: Session,
    *,
    project_slug: str,
    token: str,
    telegram_id: int,
    username: str | None,
    first_name: str | None,
) -> InvitationAcceptance:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,57}", token):
        raise InvitationError("Недействительная ссылка.")

    project = _get_project(session, project_slug)

    token_hash = hashlib.sha256(token.encode()).hexdigest()

    invitation = session.scalar(
        select(ProjectInvitation)
        .where(
            ProjectInvitation.project_id == project.id,
            ProjectInvitation.token_hash == token_hash,
        )
        .with_for_update()
    )

    now = datetime.now(timezone.utc)

    if invitation is None:
        raise InvitationError("Недействительная ссылка.")

    if invitation.revoked_at is not None:
        raise InvitationError("Приглашение отозвано.")

    if invitation.expires_at <= now:
        raise InvitationError("Срок действия приглашения истёк.")

    try:
        _check_manage_permission(
            session,
            invitation.created_by_id,
            project.id,
        )
    except PermissionError:
        raise InvitationError("Приглашение больше не действительно.") from None

    existing_membership = session.get(
        ProjectMember,
        (project.id, telegram_id),
    )

    if existing_membership is not None:
        user = session.get(User, telegram_id)

        if user is not None:
            user.username = username
            user.first_name = first_name

        return InvitationAcceptance(
            role=existing_membership.role,
            newly_added=False,
        )

    if invitation.max_uses is not None and invitation.uses_count >= invitation.max_uses:
        raise InvitationError("Лимит приглашения исчерпан.")

    user_insert = (
        insert(User)
        .values(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
        )
        .on_conflict_do_nothing(
            index_elements=[User.telegram_id],
        )
    )

    session.execute(user_insert)

    user = session.get(User, telegram_id)
    user.username = username
    user.first_name = first_name

    membership_insert = (
        insert(ProjectMember)
        .values(
            project_id=project.id,
            user_id=telegram_id,
            role=invitation.role,
        )
        .on_conflict_do_nothing(
            index_elements=[
                ProjectMember.project_id,
                ProjectMember.user_id,
            ],
        )
        .returning(ProjectMember.user_id)
    )

    added_user_id = session.scalar(membership_insert)

    if added_user_id is not None:
        invitation.uses_count += 1

        return InvitationAcceptance(
            role=invitation.role,
            newly_added=True,
        )

    existing_role = session.scalar(
        select(ProjectMember.role).where(
            ProjectMember.project_id == project.id,
            ProjectMember.user_id == telegram_id,
        )
    )

    return InvitationAcceptance(
        role=existing_role,
        newly_added=False,
    )


def revoke_invitation(
    session: Session,
    *,
    project_slug: str,
    revoked_by_id: int,
    invitation_id: int,
) -> None:
    project = _get_project(session, project_slug)

    _check_manage_permission(
        session,
        revoked_by_id,
        project.id,
    )

    invitation = session.scalar(
        select(ProjectInvitation)
        .where(
            ProjectInvitation.id == invitation_id,
            ProjectInvitation.project_id == project.id,
        )
        .with_for_update()
    )

    if invitation is None:
        raise InvitationError("Приглашение не найдено.")

    if invitation.revoked_at is None:
        invitation.revoked_at = datetime.now(timezone.utc)


def list_active_invitations(
    session: Session,
    *,
    project_slug: str,
    requested_by_id: int,
) -> list[InvitationInfo]:
    project = _get_project(session, project_slug)

    _check_manage_permission(
        session,
        requested_by_id,
        project.id,
    )

    now = datetime.now(timezone.utc)

    statement = (
        select(ProjectInvitation)
        .where(
            ProjectInvitation.project_id == project.id,
            ProjectInvitation.revoked_at.is_(None),
            ProjectInvitation.expires_at > now,
            or_(
                ProjectInvitation.max_uses.is_(None),
                ProjectInvitation.uses_count < ProjectInvitation.max_uses,
            ),
        )
        .order_by(
            ProjectInvitation.created_at.desc(),
            ProjectInvitation.id.desc(),
        )
    )

    invitations = session.scalars(statement).all()

    return [
        InvitationInfo(
            id=invitation.id,
            role=invitation.role,
            created_by_id=invitation.created_by_id,
            expires_at=invitation.expires_at,
            uses_count=invitation.uses_count,
            max_uses=invitation.max_uses,
        )
        for invitation in invitations
    ]
