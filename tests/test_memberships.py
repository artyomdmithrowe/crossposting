from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.models import Project, ProjectMember, User


@pytest.fixture
def db_session():
    engine = create_engine("postgresql+psycopg:///crossposting_dev")

    with engine.connect() as connection:
        transaction = connection.begin()

        try:
            with Session(
                bind=connection,
                join_transaction_mode="create_savepoint",
            ) as session:
                yield session
        finally:
            transaction.rollback()

    engine.dispose()


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
