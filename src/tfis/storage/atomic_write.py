from __future__ import annotations

import os
import time
from pathlib import Path
from uuid import uuid4


def atomic_write_text(
    path: str | Path,
    content: str,
    *,
    encoding: str = "utf-8",
    newline: str | None = "\n",
    attempts: int = 5,
    retry_delay_seconds: float = 0.05,
) -> Path:
    """Write text via a unique temp file and atomic replace.

    Windows can briefly deny replacing a file when another TFIS process,
    antivirus scanner, or dashboard reader has a handle open. Retrying a unique
    temp file preserves atomic visibility without making concurrent writers
    fight over the same ``.tmp`` path.
    """
    if attempts < 1:
        raise ValueError("attempts must be at least 1")

    target_path = Path(path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = (
        target_path.parent
        / f".{target_path.name}.{os.getpid()}.{uuid4().hex}.tmp"
    )
    try:
        temp_path.write_text(content, encoding=encoding, newline=newline)
        for attempt in range(attempts):
            try:
                os.replace(temp_path, target_path)
                return target_path
            except PermissionError:
                if attempt == attempts - 1:
                    raise
                time.sleep(retry_delay_seconds * (attempt + 1))
        return target_path
    finally:
        if temp_path.exists():
            temp_path.unlink()
