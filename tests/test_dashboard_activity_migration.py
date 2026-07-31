from __future__ import annotations

from pathlib import Path

from app.models.user import User


def test_user_model_exposes_last_active_at() -> None:
    assert "lastActiveAt" in User.__table__.columns
    assert User.__table__.columns["lastActiveAt"].nullable is True


def test_last_activity_migration_is_reversible() -> None:
    migration = (
        Path(__file__).parents[1] / "alembic/versions/028_add_user_last_active_at.py"
    ).read_text()

    assert 'revision = "028"' in migration
    assert 'down_revision = "027"' in migration
    assert 'op.add_column(\n        "Users"' in migration
    assert 'op.drop_column("Users", "lastActiveAt")' in migration
