import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.database.models import Project, ProjectMember, User


def grant_admin_and_owner(
    session: Session,
    telegram_id: int,
    project_slug: str,
) -> None:
    user = session.get(User, telegram_id)

    if user is None:
        raise ValueError("Пользователь не найден")

    project = session.scalar(select(Project).where(Project.slug == project_slug))

    if project is None:
        raise ValueError("Проект не найден")

    user.is_platform_admin = True

    membership = session.get(
        ProjectMember,
        (project.id, telegram_id),
    )

    if membership is None:
        membership = ProjectMember(
            project_id=project.id,
            user_id=telegram_id,
            role="owner",
        )
        session.add(membership)
    else:
        membership.role = "owner"


def main() -> None:
    load_dotenv()

    database_url = os.getenv("DATABASE_URL")
    project_slug = os.getenv("PROJECT_SLUG")

    if not database_url or not project_slug:
        raise SystemExit("DATABASE_URL и PROJECT_SLUG должны быть настроены")

    try:
        telegram_id = int(input("Введите Telegram ID: ").strip())
    except ValueError as exc:
        raise SystemExit("Некорректный Telegram ID") from exc

    if telegram_id <= 0:
        raise SystemExit("Telegram ID пользователя должен быть положительным")

    engine = create_engine(database_url, pool_pre_ping=True)

    try:
        with Session(engine) as session:
            user = session.get(User, telegram_id)

            project = session.scalar(
                select(Project).where(Project.slug == project_slug)
            )

            if user is None:
                raise SystemExit("Пользователь не найден в базе")

            if project is None:
                raise SystemExit("Проект не найден в базе")

            print(f"\nБаза данных: {make_url(database_url).database}")
            print(f"Пользователь: {user.first_name} (@{user.username})")
            print(f"Проект: {project.name}")
            print("\nНазначаемые права:")
            print("- platform_admin")
            print("- owner")

            confirmation = input("\nДля подтверждения введите GRANT: ").strip()

            if confirmation != "GRANT":
                print("Операция отменена")
                return

            grant_admin_and_owner(
                session=session,
                telegram_id=telegram_id,
                project_slug=project_slug,
            )

            session.commit()

            print("\nПрава успешно назначены!")

    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
