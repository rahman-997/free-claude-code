from pathlib import Path

import pytest

from free_claude_code.config.admin.persistence import (
    ConfigWriteConflict,
    PreparedAdminUpdate,
    _managed_config_digest,
    commit_prepared_admin_update,
)
from free_claude_code.config.settings import Settings


def _prepared(path: Path) -> PreparedAdminUpdate:
    return PreparedAdminUpdate(
        target_values={"FCC_CONFIG_SCHEMA": "1", "MODEL": "nvidia_nim/new"},
        settings=Settings().model_copy(update={"model": "nvidia_nim/new"}),
        errors=(),
        pending_fields=(),
        path=path,
        base_digest=_managed_config_digest(path),
    )


def test_admin_commit_rejects_stale_cross_process_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from free_claude_code.config.admin import persistence

    path = tmp_path / ".env"
    path.write_text("FCC_CONFIG_SCHEMA=1\nMODEL=nvidia_nim/old\n", encoding="utf-8")
    prepared = _prepared(path)
    newer = "FCC_CONFIG_SCHEMA=1\nMODEL=groq/other-process\n"
    path.write_text(newer, encoding="utf-8")
    monkeypatch.setattr(
        persistence, "config_lock_path", lambda: tmp_path / "config.lock"
    )

    with pytest.raises(ConfigWriteConflict, match="changed in another FCC process"):
        commit_prepared_admin_update(prepared)

    assert path.read_text(encoding="utf-8") == newer


def test_admin_commit_accepts_unchanged_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from free_claude_code.config.admin import persistence

    path = tmp_path / ".env"
    path.write_text("FCC_CONFIG_SCHEMA=1\nMODEL=nvidia_nim/old\n", encoding="utf-8")
    prepared = _prepared(path)
    monkeypatch.setattr(
        persistence, "config_lock_path", lambda: tmp_path / "config.lock"
    )

    result = commit_prepared_admin_update(prepared)

    assert result["applied"] is True
    assert "MODEL=nvidia_nim/new" in path.read_text(encoding="utf-8")
