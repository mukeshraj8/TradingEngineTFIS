from __future__ import annotations

import os
from pathlib import Path

import pytest

from tfis.storage.atomic_write import atomic_write_text


def test_atomic_write_text_writes_target_and_removes_temp_files(tmp_path: Path) -> None:
    target = tmp_path / "state" / "value.json"

    result = atomic_write_text(target, '{"ok": true}\n')

    assert result == target
    assert target.read_text(encoding="utf-8") == '{"ok": true}\n'
    assert list(tmp_path.rglob("*.tmp")) == []


def test_atomic_write_text_retries_transient_replace_permission_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import tfis.storage.atomic_write as atomic_write_module

    target = tmp_path / "events.jsonl"
    real_replace = os.replace
    calls = 0

    def flaky_replace(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise PermissionError("transient file contention")
        real_replace(src, dst)

    monkeypatch.setattr(atomic_write_module.os, "replace", flaky_replace)
    monkeypatch.setattr(atomic_write_module.time, "sleep", lambda _seconds: None)

    atomic_write_text(target, "one\n")

    assert calls == 2
    assert target.read_text(encoding="utf-8") == "one\n"
    assert list(tmp_path.rglob("*.tmp")) == []


def test_atomic_write_text_reraises_after_exhausted_permission_retries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import tfis.storage.atomic_write as atomic_write_module

    target = tmp_path / "events.jsonl"
    calls = 0

    def blocked_replace(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:
        nonlocal calls
        calls += 1
        raise PermissionError("persistent file contention")

    monkeypatch.setattr(atomic_write_module.os, "replace", blocked_replace)
    monkeypatch.setattr(atomic_write_module.time, "sleep", lambda _seconds: None)

    with pytest.raises(PermissionError, match="persistent file contention"):
        atomic_write_text(target, "one\n", attempts=3)

    assert calls == 3
    assert not target.exists()
    assert list(tmp_path.rglob("*.tmp")) == []
