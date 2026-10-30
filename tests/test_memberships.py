from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.database.models import Project, ProjectMember, User
from app.services.registration import check_access_and_update_profile
from scripts.bootstrap_admin import grant_admin_and_owner


def test_multiple_owners_and_projects(db_session):
    football = Project(
        slug=f"test_fb_{uuid4().hex[:12]}",
        name="Тестовый футбольный проект",
    )

    photon = Project(
        slug=f"test_ph_{uuid4().hex[:12]}",
        name="Тестовый Фотон",
    )

    artyom = User(
        telegram_id=-101,
        username="test_artyom",
        first_name="Артём",
    )

    pavel = User(
        telegram_id=-102,
        username="test_pavel",
        first_name="Павел",
    )

    db_session.add_all([football, photon, artyom, pavel])

    db_session.add_all(
        [
            ProjectMember(
                project=football,
                user=artyom,
                role="owner",
            ),
            ProjectMember(
                project=football,
                user=pavel,
                role="owner",
            ),
            ProjectMember(
                project=photon,
                user=artyom,
                role="editor",
            ),
        ]
    )

    db_session.flush()

    assert len(football.members) == 2
    assert all(member.role == "owner" for member in football.members)

    assert len(artyom.memberships) == 2

    assert {member.role for member in artyom.memberships} == {"owner", "editor"}


def test_duplicate_membership_rejected(db_session):
    project = Project(
        slug=f"test_dup_{uuid4().hex[:12]}",
        name="Тестовый проект",
    )

    user = User(
        telegram_id=-103,
        username="test_user",
    )

    db_session.add_all([project, user])
    db_session.flush()

    db_session.add_all(
        [
            ProjectMember(
                project_id=project.id,
                user_id=user.telegram_id,
                role="owner",
            ),
            ProjectMember(
                project_id=project.id,
                user_id=user.telegram_id,
                role="editor",
            ),
        ]
    )

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_invalid_role_rejected(db_session):
    project = Project(
        slug=f"test_role_{uuid4().hex[:12]}",
        name="Тестовый проект",
    )

    user = User(
        telegram_id=-104,
        username="test_editor",
    )

    db_session.add_all([project, user])
    db_session.flush()

    membership = ProjectMember(
        project_id=project.id,
        user_id=user.telegram_id,
        role="admin",
    )

    db_session.add(membership)

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_telegram_id_is_required(db_session):
    # SQLAlchemy mustn't generate Telegram ID.
    assert User.__table__.c.telegram_id.autoincrement is False

    # PostgreSQL must reject users without Telegram ID.
    with pytest.raises(IntegrityError):
        db_session.execute(
            text("INSERT INTO users (username) VALUES (:username)"),
            {"username": f"missing_id_{uuid4().hex[:12]}"},
        )


def test_existing_user_profile_and_access(db_session):
    project = Project(
        slug=f"test_access_{uuid4().hex[:12]}",
        name="Тестовый проект",
    )

    telegram_id = -(uuid4().int % 10**12 + 1)

    user = User(
        telegram_id=telegram_id,
        username="old_username",
        first_name="Старое имя",
    )

    db_session.add_all([project, user])
    db_session.flush()

    membership = ProjectMember(
        project_id=project.id,
        user_id=telegram_id,
        role="owner",
    )

    db_session.add(membership)
    db_session.flush()

    role = check_access_and_update_profile(
        session=db_session,
        telegram_id=telegram_id,
        username="new_username",
        first_name="Новое имя",
        project_slug=project.slug,
    )

    assert role == "owner"

    db_session.flush()
    db_session.refresh(user)

    assert user.username == "new_username"
    assert user.first_name == "Новое имя"


def test_platform_admin_is_not_granted_automatically(db_session):
    project = Project(
        slug=f"test_admin_{uuid4().hex[:12]}",
        name="Тестовый проект",
    )

    telegram_id = -(uuid4().int % 10**12 + 1)

    user = User(
        telegram_id=telegram_id,
        username="test_admin",
        first_name="Тест",
    )

    db_session.add_all([project, user])
    db_session.flush()

    assert user.is_platform_admin is False

    role = check_access_and_update_profile(
        session=db_session,
        telegram_id=telegram_id,
        username="updated_username",
        first_name="Тест",
        project_slug=project.slug,
    )

    assert role is None
    assert user.is_platform_admin is False

    # Set is_platform_admin to True.
    user.is_platform_admin = True
    db_session.flush()

    # Repeated /start must not change is_platform_admin.
    check_access_and_update_profile(
        session=db_session,
        telegram_id=telegram_id,
        username="another_username",
        first_name="Тест",
        project_slug=project.slug,
    )

    assert user.is_platform_admin is True


def test_unknown_user_is_not_registered(db_session):
    project = Project(
        slug=f"test_unknown_{uuid4().hex[:12]}",
        name="Тестовый проект",
    )

    db_session.add(project)
    db_session.flush()

    unknown_id = -(uuid4().int % 10**12 + 1)

    role = check_access_and_update_profile(
        session=db_session,
        telegram_id=unknown_id,
        username="unknown_user",
        first_name="Неизвестный",
        project_slug=project.slug,
    )

    assert role is None
    assert db_session.get(User, unknown_id) is None


def test_bootstrap_admin_is_idempotent(db_session):
    project = Project(
        slug=f"test_bootstrap_{uuid4().hex[:12]}",
        name="Тестовый проект",
    )

    telegram_id = -(uuid4().int % 10**12 + 1)

    user = User(
        telegram_id=telegram_id,
        username="test_admin",
        first_name="Администратор",
    )

    db_session.add_all([project, user])
    db_session.flush()

    # First setting
    grant_admin_and_owner(
        session=db_session,
        telegram_id=telegram_id,
        project_slug=project.slug,
    )

    db_session.flush()

    # Repeating setting
    grant_admin_and_owner(
        session=db_session,
        telegram_id=telegram_id,
        project_slug=project.slug,
    )

    db_session.flush()
    db_session.refresh(user)

    memberships = db_session.scalars(
        select(ProjectMember).where(
            ProjectMember.project_id == project.id,
            ProjectMember.user_id == telegram_id,
        )
    ).all()

    assert user.is_platform_admin is True
    assert len(memberships) == 1
    assert memberships[0].role == "owner"
