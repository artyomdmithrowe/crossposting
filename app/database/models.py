from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, String
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
