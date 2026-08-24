from alembic.config import Config
from alembic.script import ScriptDirectory


def test_deployed_revision_035_is_available() -> None:
    """Production DB revision must remain resolvable by every deployed image."""
    script = ScriptDirectory.from_config(Config("alembic.ini"))

    assert script.get_revision("035") is not None
    assert script.get_revision("035").down_revision == "034"
