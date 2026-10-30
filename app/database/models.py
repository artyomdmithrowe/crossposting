from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)

    slug: Mapped[str] = mapped_column(
        String(32),
        unique=True,
    )

    name: Mapped[str] = mapped_column(
        String(120),
    )

    members: Mapped[list["ProjectMember"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )


class User(Base):
    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=False,
    )

    username: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )

    first_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    memberships: Mapped[list["ProjectMember"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )

    is_platform_admin: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=false(),
    )


class ProjectMember(Base):
    __tablename__ = "project_members"

    __table_args__ = (
        CheckConstraint(
            "role IN ('owner', 'editor')",
            name="ck_project_members_role",
        ),
    )

    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        primary_key=True,
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_id", ondelete="CASCADE"),
        primary_key=True,
    )

    role: Mapped[str] = mapped_column(String(16))

    project: Mapped["Project"] = relationship(
        back_populates="members",
    )

    user: Mapped["User"] = relationship(
        back_populates="memberships",
    )


class ProjectInvitation(Base):
    __tablename__ = "project_invitations"

    __table_args__ = (
        CheckConstraint(
            "role IN ('owner', 'editor')",
            name="ck_project_invitations_role",
        ),
        CheckConstraint(
            "max_uses IS NULL OR max_uses > 0",
            name="ck_project_invitations_max_uses",
        ),
        CheckConstraint(
            "uses_count >= 0",
            name="ck_project_invitations_uses_count",
        ),
        CheckConstraint(
            "max_uses IS NULL OR uses_count <= max_uses",
            name="ck_project_invitations_uses_limit",
        ),
        CheckConstraint(
            "role != 'owner' OR (max_uses IS NOT NULL AND max_uses = 1)",
            name="ck_project_invitations_owner_single_use",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
    )

    created_by_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_id", ondelete="RESTRICT"),
    )

    role: Mapped[str] = mapped_column(String(16))

    token_hash: Mapped[str] = mapped_column(
        String(64),
        unique=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
    )

    max_uses: Mapped[int | None] = mapped_column(
        nullable=True,
    )

    uses_count: Mapped[int] = mapped_column(
        default=0,
        server_default="0",
    )

    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class Publication(Base):
    __tablename__ = "publications"

    __table_args__ = (
        CheckConstraint(
            "source_type IN ('editor', 'forward', 'channel')",
            name="ck_publications_source_type",
        ),
        CheckConstraint(
            "status IN ('draft', 'submitted', 'cancelled')",
            name="ck_publications_status",
        ),
        CheckConstraint(
            "(source_telegram_chat_id IS NULL) = (source_telegram_message_id IS NULL)",
            name="ck_publications_source_tg_pair",
        ),
        UniqueConstraint(
            "project_id",
            "source_telegram_chat_id",
            "source_telegram_message_id",
            name="uq_publications_source_tg",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
    )

    created_by_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_id", ondelete="SET NULL"),
        nullable=True,
    )

    source_type: Mapped[str] = mapped_column(String(16))

    status: Mapped[str] = mapped_column(
        String(16),
        server_default="draft",
    )

    source_text: Mapped[str] = mapped_column(
        Text,
        server_default="",
    )

    source_payload: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        server_default="{}",
    )

    source_telegram_chat_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )

    source_telegram_message_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    deliveries: Mapped[list["PublicationDelivery"]] = relationship(
        back_populates="publication",
        cascade="all, delete-orphan",
    )


class PublicationDelivery(Base):
    __tablename__ = "publication_deliveries"

    __table_args__ = (
        CheckConstraint(
            "platform IN ('telegram', 'vk')",
            name="ck_publication_deliveries_platform",
        ),
        CheckConstraint(
            "status IN ('pending', 'publishing', 'published', 'failed')",
            name="ck_publication_deliveries_status",
        ),
        CheckConstraint(
            "attempts >= 0",
            name="ck_publication_deliveries_attempts",
        ),
        UniqueConstraint(
            "publication_id",
            "platform",
            name="uq_publication_deliveries_platform",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    publication_id: Mapped[int] = mapped_column(
        ForeignKey("publications.id", ondelete="CASCADE"),
        index=True,
    )

    platform: Mapped[str] = mapped_column(String(16))

    status: Mapped[str] = mapped_column(
        String(16),
        server_default="pending",
    )

    text_override: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    payload_override: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    destination_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )

    external_post_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    attempts: Mapped[int] = mapped_column(
        server_default="0",
    )

    last_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    publication: Mapped["Publication"] = relationship(
        back_populates="deliveries",
    )
