import hashlib
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.database.models import (
    Project,
    ProjectInvitation,
    ProjectMember,
    User,
)
from app.services.invitations import (
    InvitationError,
    accept_invitation,
    create_invitation,
    list_active_invitations,
    revoke_invitation,
)


def new_telegram_id() -> int:
    return -(uuid4().int % 10**12 + 1)


def create_test_project(
    session,
    *,
    actor_role=None,
    platform_admin=False,
):
    project = Project(
        slug=f"test_inv_{uuid4().hex[:12]}",
        name="Тестовый проект",
    )

    actor = User(
        telegram_id=new_telegram_id(),
        username="test_actor",
        first_name="Тестовый пользователь",
        is_platform_admin=platform_admin,
    )

    session.add_all([project, actor])
    session.flush()

    if actor_role is not None:
        session.add(
            ProjectMember(
                project_id=project.id,
                user_id=actor.telegram_id,
                role=actor_role,
            )
        )
        session.flush()

    return project, actor


def accept_for_user(session, project, token, telegram_id):
    return accept_invitation(
        session,
        project_slug=project.slug,
        token=token,
        telegram_id=telegram_id,
        username=f"user_{abs(telegram_id)}",
        first_name="Тест",
    )


def test_platform_admin_invites_first_owner(db_session):
    project, admin = create_test_project(
        db_session,
        platform_admin=True,
    )

    assert (
        db_session.get(
            ProjectMember,
            (project.id, admin.telegram_id),
        )
        is None
    )

    created = create_invitation(
        db_session,
        project_slug=project.slug,
        created_by_id=admin.telegram_id,
        role="owner",
    )

    invitation = db_session.get(ProjectInvitation, created.id)

    assert invitation.role == "owner"
    assert invitation.max_uses == 1
    assert invitation.uses_count == 0

    assert invitation.token_hash == hashlib.sha256(created.token.encode()).hexdigest()

    remaining = created.expires_at - datetime.now(timezone.utc)

    assert timedelta(hours=23, minutes=59) < remaining
    assert remaining <= timedelta(hours=24)

    new_owner_id = new_telegram_id()

    result = accept_for_user(
        db_session,
        project,
        created.token,
        new_owner_id,
    )

    assert result.role == "owner"
    assert result.newly_added is True

    assert db_session.get(User, new_owner_id) is not None

    membership = db_session.get(
        ProjectMember,
        (project.id, new_owner_id),
    )

    assert membership.role == "owner"
    assert invitation.uses_count == 1


def test_editor_invitation_can_be_reused(db_session):
    project, owner = create_test_project(
        db_session,
        actor_role="owner",
    )

    created = create_invitation(
        db_session,
        project_slug=project.slug,
        created_by_id=owner.telegram_id,
        role="editor",
    )

    invitation = db_session.get(ProjectInvitation, created.id)

    assert invitation.max_uses is None

    first_id = new_telegram_id()
    second_id = new_telegram_id()

    first = accept_for_user(
        db_session,
        project,
        created.token,
        first_id,
    )

    second = accept_for_user(
        db_session,
        project,
        created.token,
        second_id,
    )

    assert first.role == "editor"
    assert second.role == "editor"

    assert first.newly_added is True
    assert second.newly_added is True

    assert invitation.uses_count == 2

    repeated = accept_for_user(
        db_session,
        project,
        created.token,
        first_id,
    )

    assert repeated.role == "editor"
    assert repeated.newly_added is False
    assert invitation.uses_count == 2


@pytest.mark.parametrize("actor_role", [None, "editor"])
def test_only_owner_or_admin_can_create_invitation(
    db_session,
    actor_role,
):
    project, actor = create_test_project(
        db_session,
        actor_role=actor_role,
    )

    with pytest.raises(PermissionError):
        create_invitation(
            db_session,
            project_slug=project.slug,
            created_by_id=actor.telegram_id,
            role="editor",
        )


def test_existing_role_is_not_changed(db_session):
    project, owner = create_test_project(
        db_session,
        actor_role="owner",
    )

    editor_id = new_telegram_id()

    db_session.add(
        User(
            telegram_id=editor_id,
            username="existing_editor",
        )
    )

    db_session.add(
        ProjectMember(
            project_id=project.id,
            user_id=editor_id,
            role="editor",
        )
    )

    db_session.flush()

    created = create_invitation(
        db_session,
        project_slug=project.slug,
        created_by_id=owner.telegram_id,
        role="owner",
    )

    result = accept_for_user(
        db_session,
        project,
        created.token,
        editor_id,
    )

    invitation = db_session.get(ProjectInvitation, created.id)

    assert result.role == "editor"
    assert result.newly_added is False
    assert invitation.uses_count == 0

    membership = db_session.get(
        ProjectMember,
        (project.id, editor_id),
    )

    assert membership.role == "editor"


def test_owner_invitation_can_be_used_only_once(db_session):
    project, owner = create_test_project(
        db_session,
        actor_role="owner",
    )

    created = create_invitation(
        db_session,
        project_slug=project.slug,
        created_by_id=owner.telegram_id,
        role="owner",
    )

    accept_for_user(
        db_session,
        project,
        created.token,
        new_telegram_id(),
    )

    rejected_user_id = new_telegram_id()

    with pytest.raises(InvitationError):
        accept_for_user(
            db_session,
            project,
            created.token,
            rejected_user_id,
        )

    assert db_session.get(User, rejected_user_id) is None


def test_expired_invitation_is_rejected(db_session):
    project, owner = create_test_project(
        db_session,
        actor_role="owner",
    )

    created = create_invitation(
        db_session,
        project_slug=project.slug,
        created_by_id=owner.telegram_id,
        role="editor",
    )

    invitation = db_session.get(ProjectInvitation, created.id)

    invitation.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)

    db_session.flush()

    rejected_user_id = new_telegram_id()

    with pytest.raises(InvitationError):
        accept_for_user(
            db_session,
            project,
            created.token,
            rejected_user_id,
        )

    assert db_session.get(User, rejected_user_id) is None
    assert invitation.uses_count == 0


def test_revoked_invitation_is_rejected(db_session):
    project, owner = create_test_project(
        db_session,
        actor_role="owner",
    )

    created = create_invitation(
        db_session,
        project_slug=project.slug,
        created_by_id=owner.telegram_id,
        role="editor",
    )

    revoke_invitation(
        db_session,
        project_slug=project.slug,
        revoked_by_id=owner.telegram_id,
        invitation_id=created.id,
    )

    invitation = db_session.get(ProjectInvitation, created.id)

    assert invitation.revoked_at is not None

    rejected_user_id = new_telegram_id()

    with pytest.raises(InvitationError):
        accept_for_user(
            db_session,
            project,
            created.token,
            rejected_user_id,
        )

    assert db_session.get(User, rejected_user_id) is None


def test_invitation_cannot_be_used_in_another_project(db_session):
    project, owner = create_test_project(
        db_session,
        actor_role="owner",
    )

    another_project = Project(
        slug=f"test_other_{uuid4().hex[:12]}",
        name="Другой проект",
    )

    db_session.add(another_project)
    db_session.flush()

    created = create_invitation(
        db_session,
        project_slug=project.slug,
        created_by_id=owner.telegram_id,
        role="editor",
    )

    rejected_user_id = new_telegram_id()

    with pytest.raises(InvitationError):
        accept_for_user(
            db_session,
            another_project,
            created.token,
            rejected_user_id,
        )

    assert db_session.get(User, rejected_user_id) is None


def test_invitation_stops_working_if_creator_loses_rights(
    db_session,
):
    project, owner = create_test_project(
        db_session,
        actor_role="owner",
    )

    created = create_invitation(
        db_session,
        project_slug=project.slug,
        created_by_id=owner.telegram_id,
        role="editor",
    )

    membership = db_session.get(
        ProjectMember,
        (project.id, owner.telegram_id),
    )

    membership.role = "editor"
    db_session.flush()

    rejected_user_id = new_telegram_id()

    with pytest.raises(InvitationError):
        accept_for_user(
            db_session,
            project,
            created.token,
            rejected_user_id,
        )

    assert db_session.get(User, rejected_user_id) is None


def _prepare_invitation_listing(db_session):
    suffix = uuid4().hex[:12]

    project = Project(
        slug=f"list_{suffix}",
        name="Тестовый проект приглашений",
    )

    owner = User(
        telegram_id=-(uuid4().int % 10**12 + 1),
        username="listing_owner",
    )

    editor = User(
        telegram_id=-(uuid4().int % 10**12 + 1),
        username="listing_editor",
    )

    db_session.add_all([project, owner, editor])
    db_session.flush()

    db_session.add_all(
        [
            ProjectMember(
                project_id=project.id,
                user_id=owner.telegram_id,
                role="owner",
            ),
            ProjectMember(
                project_id=project.id,
                user_id=editor.telegram_id,
                role="editor",
            ),
        ]
    )

    db_session.flush()

    return project, owner, editor


def test_list_only_active_invitations(db_session):
    project, owner, _ = _prepare_invitation_listing(db_session)

    def create(role):
        return create_invitation(
            db_session,
            project_slug=project.slug,
            created_by_id=owner.telegram_id,
            role=role,
        )

    active = create("editor")
    expired = create("editor")
    revoked = create("editor")
    used = create("owner")

    expired_record = db_session.get(ProjectInvitation, expired.id)
    expired_record.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)

    revoked_record = db_session.get(ProjectInvitation, revoked.id)
    revoked_record.revoked_at = datetime.now(timezone.utc)

    used_record = db_session.get(ProjectInvitation, used.id)
    used_record.uses_count = 1

    db_session.flush()

    invitations = list_active_invitations(
        db_session,
        project_slug=project.slug,
        requested_by_id=owner.telegram_id,
    )

    assert len(invitations) == 1
    assert invitations[0].id == active.id
    assert invitations[0].role == "editor"


def test_editor_cannot_list_invitations(db_session):
    project, owner, editor = _prepare_invitation_listing(db_session)

    create_invitation(
        db_session,
        project_slug=project.slug,
        created_by_id=owner.telegram_id,
        role="editor",
    )

    with pytest.raises(PermissionError):
        list_active_invitations(
            db_session,
            project_slug=project.slug,
            requested_by_id=editor.telegram_id,
        )


def test_invitations_are_project_scoped(db_session):
    project, owner, _ = _prepare_invitation_listing(db_session)

    other_project = Project(
        slug=f"other_{uuid4().hex[:12]}",
        name="Другой тестовый проект",
    )

    db_session.add(other_project)
    db_session.flush()

    db_session.add(
        ProjectMember(
            project_id=other_project.id,
            user_id=owner.telegram_id,
            role="owner",
        )
    )
    db_session.flush()

    first = create_invitation(
        db_session,
        project_slug=project.slug,
        created_by_id=owner.telegram_id,
        role="editor",
    )

    second = create_invitation(
        db_session,
        project_slug=other_project.slug,
        created_by_id=owner.telegram_id,
        role="editor",
    )

    invitations = list_active_invitations(
        db_session,
        project_slug=project.slug,
        requested_by_id=owner.telegram_id,
    )

    assert [invitation.id for invitation in invitations] == [first.id]
    assert second.id not in {invitation.id for invitation in invitations}


def test_owner_invitation_is_idempotent_for_recipient(db_session):
    project = Project(
        slug=f"test_owner_inv_{uuid4().hex[:12]}",
        name="Тестовый проект",
    )

    owner_id = -(uuid4().int % 10**12 + 1)
    recipient_id = owner_id - 1
    another_user_id = owner_id - 2

    owner = User(
        telegram_id=owner_id,
        username="test_owner",
        first_name="Владелец",
    )

    db_session.add_all([project, owner])
    db_session.flush()

    db_session.add(
        ProjectMember(
            project_id=project.id,
            user_id=owner_id,
            role="owner",
        )
    )
    db_session.flush()

    invitation = create_invitation(
        db_session,
        project_slug=project.slug,
        created_by_id=owner_id,
        role="owner",
    )

    # First accept: new user becomes owner.
    first_result = accept_invitation(
        db_session,
        project_slug=project.slug,
        token=invitation.token,
        telegram_id=recipient_id,
        username="test_recipient",
        first_name="Получатель",
    )

    assert first_result.newly_added is True
    assert first_result.role == "owner"

    db_session.flush()

    # Repeated accepting from the same user.
    second_result = accept_invitation(
        db_session,
        project_slug=project.slug,
        token=invitation.token,
        telegram_id=recipient_id,
        username="test_recipient",
        first_name="Получатель",
    )

    assert second_result.newly_added is False
    assert second_result.role == "owner"

    db_session.flush()

    # Link must be revoked.
    stored_invitation = db_session.get(
        ProjectInvitation,
        invitation.id,
    )

    assert stored_invitation.uses_count == 1
    assert stored_invitation.max_uses == 1

    # Another user cannot accept the invitation.
    with pytest.raises(InvitationError, match="Лимит"):
        accept_invitation(
            db_session,
            project_slug=project.slug,
            token=invitation.token,
            telegram_id=another_user_id,
            username="another_user",
            first_name="Другой",
        )

    # User aren't created with thr wrong accepting.
    assert db_session.get(User, another_user_id) is None
