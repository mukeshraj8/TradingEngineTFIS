from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path


_DAY_DIRECTORY_RE = re.compile(r"\d{4}-\d{2}-\d{2}$")
_STAGE_SNAPSHOT_RE = re.compile(r"-(\d{4})-(\d{4}-\d{2}-\d{2})$")
_STAGE_KEY_ORDER = {"0916": 1, "0925": 2, "0930": 3}


@dataclass(frozen=True, slots=True)
class PaperSupervisedStageArtifactPaths:
    monthly_status_stage_json: Path | None
    trade_decision_explainer_stage_json: Path | None


_SCHEDULED_RUN_METADATA_FILENAME = "scheduled_run_metadata.json"


def iter_strategy_day_dirs(artifact_root: Path) -> tuple[Path, ...]:
    if not artifact_root.exists():
        return ()
    return tuple(
        sorted(
            (
                path
                for path in artifact_root.iterdir()
                if path.is_dir() and _DAY_DIRECTORY_RE.fullmatch(path.name)
            ),
            reverse=True,
        )
    )


def find_supervised_final_session_dir(
    day_dir: Path,
    *,
    session_id_prefix: str,
) -> Path | None:
    final_name = f"{session_id_prefix}-{day_dir.name}"
    for child in day_dir.iterdir():
        if child.is_dir() and child.name == final_name:
            return child
    return None


def supervised_session_metadata_path(session_dir: Path | None) -> Path | None:
    if session_dir is None:
        return None
    return session_dir / _SCHEDULED_RUN_METADATA_FILENAME


def supervised_session_is_complete(session_dir: Path | None) -> bool:
    metadata_path = supervised_session_metadata_path(session_dir)
    return bool(metadata_path is not None and metadata_path.exists())


def find_supervised_stage_dirs(
    day_dir: Path,
    *,
    session_id_prefix: str,
) -> tuple[Path, ...]:
    return tuple(
        sorted(
            (
                child
                for child in day_dir.iterdir()
                if child.is_dir()
                and child.name.startswith(session_id_prefix)
                and _STAGE_SNAPSHOT_RE.search(child.name)
                and (child / "snapshot_preflight_summary.json").exists()
            ),
            key=lambda item: (
                _STAGE_KEY_ORDER.get(_extract_stage_key(item.name), 99),
                item.name,
            ),
        )
    )


def find_latest_supervised_session_dir(
    day_root: Path,
    *,
    session_date: date,
    session_id_prefix: str | None = None,
) -> Path | None:
    suffix = session_date.isoformat()
    candidates = sorted(
        (
            path
            for path in day_root.iterdir()
            if path.is_dir()
            and path.name.endswith(suffix)
            and (not session_id_prefix or path.name.startswith(session_id_prefix))
        ),
        key=lambda path: path.stat().st_mtime,
    )
    if not candidates:
        return None
    return candidates[-1]


def iter_trade_decision_summary_paths(session_dir: Path) -> tuple[Path, ...]:
    return tuple(sorted(session_dir.rglob("trade_decision_summary.json")))


def iter_session_branch_dirs(session_dir: Path) -> tuple[Path, ...]:
    if not session_dir.exists():
        return ()
    return tuple(
        sorted(path for path in session_dir.iterdir() if path.is_dir())
    )


def iter_session_branch_explainer_paths(session_dir: Path) -> tuple[Path, ...]:
    paths: list[Path] = []
    for branch_dir in iter_session_branch_dirs(session_dir):
        final_path = branch_dir / "trade_decision_explainer.json"
        if final_path.exists():
            paths.append(final_path)
            continue
        stage_paths = sorted(branch_dir.glob("trade_decision_explainer_stage_*.json"))
        if stage_paths:
            paths.append(stage_paths[-1])
    return tuple(paths)


def find_preferred_supervised_stage_dir(
    day_dir: Path,
    *,
    session_id_prefix: str,
    preferred_stage_key: str = "0930",
) -> Path | None:
    stage_dirs = find_supervised_stage_dirs(
        day_dir,
        session_id_prefix=session_id_prefix,
    )
    for stage_dir in stage_dirs:
        if _extract_stage_key(stage_dir.name) == preferred_stage_key:
            return stage_dir
    return stage_dirs[-1] if stage_dirs else None


def resolve_supervised_stage_artifact_paths(
    final_session_dir: Path | None,
    *,
    stage_key: str,
) -> PaperSupervisedStageArtifactPaths:
    if final_session_dir is None:
        return PaperSupervisedStageArtifactPaths(
            monthly_status_stage_json=None,
            trade_decision_explainer_stage_json=None,
        )
    return PaperSupervisedStageArtifactPaths(
        monthly_status_stage_json=final_session_dir / f"monthly_status_stage_{stage_key}.json",
        trade_decision_explainer_stage_json=(
            final_session_dir / f"trade_decision_explainer_stage_{stage_key}.json"
        ),
    )


def _extract_stage_key(name: str) -> str | None:
    match = _STAGE_SNAPSHOT_RE.search(name)
    if match is None:
        return None
    return match.group(1)
