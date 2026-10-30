from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import Project, ProjectMember, User


def check_access_and_update_profile(
    session: Session,
    telegram_id: int,
    username: str | None,
    first_name: str | None,
    project_slug: str,
) -> str | None:
    user = session.get(User, telegram_id)

    if user is None:
        return None

    user.username = username
    user.first_name = first_name

    return session.scalar(
        select(ProjectMember.role)
        .join(Project, ProjectMember.project_id == Project.id)
        .where(
            Project.slug == project_slug,
            ProjectMember.user_id == telegram_id,
        )
    )
