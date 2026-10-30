from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.database.models import (
    Project,
    Publication,
    PublicationDelivery,
    User,
)


def create_test_project(db_session):
    project = Project(
        slug=f"test_pub_{uuid4().hex[:12]}",
        name="Тестовый проект",
    )

    db_session.add(project)
    db_session.flush()

    return project


def test_publication_with_two_deliveries(db_session):
    """One publication can be delivered to Telegram and VK."""
    project = create_test_project(db_session)

    author = User(
        telegram_id=-(uuid4().int % 10**12 + 1),
        username="test_author",
    )

    db_session.add(author)
    db_session.flush()

    publication = Publication(
        project_id=project.id,
        created_by_id=author.telegram_id,
        source_type="editor",
        source_text="Тестовая публикация",
        source_payload={"entities": []},
    )

    publication.deliveries = [
        PublicationDelivery(
            platform="telegram",
        ),
        PublicationDelivery(
            platform="vk",
            text_override="Отдельный текст для ВК",
        ),
    ]

    db_session.add(publication)
    db_session.flush()

    assert publication.id is not None
    assert publication.status == "draft"
    assert len(publication.deliveries) == 2

    deliveries = {delivery.platform: delivery for delivery in publication.deliveries}

    assert set(deliveries) == {"telegram", "vk"}

    assert deliveries["telegram"].status == "pending"
    assert deliveries["vk"].status == "pending"

    assert deliveries["vk"].text_override == "Отдельный текст для ВК"


def test_duplicate_platform_rejected(db_session):
    """One publication cannot have two deliveries to VK."""
    project = create_test_project(db_session)

    publication = Publication(
        project_id=project.id,
        source_type="editor",
        source_text="Тест",
    )

    publication.deliveries = [
        PublicationDelivery(platform="vk"),
        PublicationDelivery(platform="vk"),
    ]

    db_session.add(publication)

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_duplicate_telegram_source_rejected(db_session):
    """The same Telegram message cannot be imported twice."""
    project = create_test_project(db_session)

    first = Publication(
        project_id=project.id,
        source_type="channel",
        source_telegram_chat_id=-1001234567890,
        source_telegram_message_id=42,
    )

    db_session.add(first)
    db_session.flush()

    duplicate = Publication(
        project_id=project.id,
        source_type="forward",
        source_telegram_chat_id=-1001234567890,
        source_telegram_message_id=42,
    )

    db_session.add(duplicate)

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_invalid_source_type_rejected(db_session):
    """Unknown publication source types must be rejected."""
    project = create_test_project(db_session)

    publication = Publication(
        project_id=project.id,
        source_type="unknown",
        source_text="Тест",
    )

    db_session.add(publication)

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_invalid_delivery_status_rejected(db_session):
    """Only supported delivery statuses are allowed."""
    project = create_test_project(db_session)

    publication = Publication(
        project_id=project.id,
        source_type="editor",
        source_text="Тест",
    )

    publication.deliveries = [
        PublicationDelivery(
            platform="vk",
            status="unknown",
        ),
    ]

    db_session.add(publication)

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_incomplete_telegram_source_rejected(db_session):
    """Telegram chat ID and message ID must be provided together."""
    project = create_test_project(db_session)

    publication = Publication(
        project_id=project.id,
        source_type="channel",
        source_telegram_chat_id=-1001234567890,
    )

    db_session.add(publication)

    with pytest.raises(IntegrityError):
        db_session.flush()
