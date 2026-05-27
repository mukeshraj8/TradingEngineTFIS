from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, fields, is_dataclass
from datetime import date, datetime, time
from enum import Enum
from pathlib import Path
from typing import Any

from .models import PaperSessionState


_BUNDLE_VERSION = 1
_BUNDLE_MANIFEST_NAME = "replay_bundle_manifest.json"
_SHARED_ARTIFACTS = (
    "session_manifest.json",
    "audit_events.jsonl",
    "decision_summary.json",
)
_TERMINAL_ARTIFACTS = {
    PaperSessionState.ORDER_PLANNED: "paper_order_plan.json",
    PaperSessionState.NO_TRADE: "no_trade_summary.json",
    PaperSessionState.ABORTED: "abort_summary.json",
}


@dataclass(frozen=True, slots=True)
class S23PaperReplayBundleFile:
    relative_path: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class S23PaperReplayBundleManifest:
    bundle_version: int
    created_at: datetime
    strategy_code: str
    session_id: str
    session_date: date
    terminal_state: PaperSessionState
    terminal_reason_code: str | None
    source_artifact_root: str
    source_session_directory: str
    artifact_files: tuple[S23PaperReplayBundleFile, ...]


@dataclass(frozen=True, slots=True)
class S23PaperReplayBundleValidationResult:
    is_valid: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    manifest: S23PaperReplayBundleManifest | None
    terminal_state: PaperSessionState | None
    terminal_reason_code: str | None


@dataclass(frozen=True, slots=True)
class S23PaperReplayBundleSummary:
    bundle_valid: bool
    session_id: str | None
    strategy_code: str | None
    terminal_state: PaperSessionState | None
    terminal_reason_code: str | None
    audit_transition_count: int
    audit_transitions: tuple[str, ...]
    validation_errors: tuple[str, ...]
    validation_warnings: tuple[str, ...]


class S23PaperReplayBundleManager:
    def __init__(self, manifest_name: str = _BUNDLE_MANIFEST_NAME) -> None:
        self._manifest_name = manifest_name

    def create_bundle(
        self,
        session_directory: str | Path,
        *,
        created_at: datetime | None = None,
        source_artifact_root: str | Path | None = None,
    ) -> Path:
        bundle_directory = Path(session_directory)
        if not bundle_directory.exists():
            raise FileNotFoundError(
                f"S23 paper session artifact directory does not exist: {bundle_directory}"
            )

        decision_summary = self._load_json(bundle_directory / "decision_summary.json")
        strategy_code = str(decision_summary.get("strategy_code", ""))
        if strategy_code != "S23":
            raise ValueError(
                "Replay bundles currently support S23 paper sessions only."
            )

        session_id = str(decision_summary.get("session_id", ""))
        session_date = self._parse_date(decision_summary["session_date"])
        terminal_state = PaperSessionState(str(decision_summary["state"]))
        terminal_reason_code = self._optional_text(
            decision_summary.get("terminal_reason_code")
        )

        required_paths = self._required_artifacts_for_directory(
            bundle_directory,
            terminal_state=terminal_state,
            selected_contract_required=bool(
                decision_summary.get("selected_contract_available", False)
            ),
        )
        for relative_path in required_paths:
            artifact_path = bundle_directory / relative_path
            if not artifact_path.exists():
                raise ValueError(
                    f"Replay bundle requires missing artifact: {relative_path}"
                )

        artifact_files = tuple(
            self._file_record(bundle_directory, relative_path)
            for relative_path in sorted(required_paths)
        )
        resolved_root = Path(source_artifact_root) if source_artifact_root is not None else self._derive_source_root(bundle_directory)
        manifest = S23PaperReplayBundleManifest(
            bundle_version=_BUNDLE_VERSION,
            created_at=created_at or datetime.now().astimezone(),
            strategy_code=strategy_code,
            session_id=session_id,
            session_date=session_date,
            terminal_state=terminal_state,
            terminal_reason_code=terminal_reason_code,
            source_artifact_root=str(resolved_root),
            source_session_directory=str(bundle_directory),
            artifact_files=artifact_files,
        )
        manifest_path = bundle_directory / self._manifest_name
        self._write_json(manifest_path, manifest)
        return manifest_path

    def validate_bundle(
        self,
        bundle_directory: str | Path,
    ) -> S23PaperReplayBundleValidationResult:
        directory = Path(bundle_directory)
        manifest_path = directory / self._manifest_name
        if not manifest_path.exists():
            return S23PaperReplayBundleValidationResult(
                is_valid=False,
                errors=("missing_replay_bundle_manifest",),
                warnings=(),
                manifest=None,
                terminal_state=None,
                terminal_reason_code=None,
            )

        manifest = self._load_bundle_manifest(manifest_path)
        errors: list[str] = []
        warnings: list[str] = []

        if manifest.strategy_code != "S23":
            errors.append("unsupported_strategy_code")

        decision_path = directory / "decision_summary.json"
        if not decision_path.exists():
            errors.append("missing_required_artifact:decision_summary.json")
            return S23PaperReplayBundleValidationResult(
                is_valid=False,
                errors=tuple(errors),
                warnings=tuple(warnings),
                manifest=manifest,
                terminal_state=manifest.terminal_state,
                terminal_reason_code=manifest.terminal_reason_code,
            )

        decision_summary = self._load_json(decision_path)
        decision_state = self._parse_state(decision_summary.get("state"))
        decision_terminal_reason = self._optional_text(
            decision_summary.get("terminal_reason_code")
        )
        if decision_state is None:
            errors.append("invalid_decision_state")
        elif decision_state is not manifest.terminal_state:
            errors.append("terminal_state_mismatch")

        selected_contract_required = bool(
            decision_summary.get("selected_contract_available", False)
        )
        expected_paths = self._required_artifacts_for_state(
            manifest.terminal_state,
            selected_contract_required=selected_contract_required,
        )
        actual_terminal_paths = {
            path
            for path in _TERMINAL_ARTIFACTS.values()
            if (directory / path).exists()
        }
        expected_terminal_path = _TERMINAL_ARTIFACTS[manifest.terminal_state]
        if expected_terminal_path not in actual_terminal_paths:
            errors.append(f"missing_required_artifact:{expected_terminal_path}")
        unexpected_terminal_paths = actual_terminal_paths - {expected_terminal_path}
        if unexpected_terminal_paths:
            errors.append("terminal_artifact_mismatch")

        manifest_paths = {item.relative_path for item in manifest.artifact_files}
        missing_manifest_entries = expected_paths - manifest_paths
        for relative_path in sorted(missing_manifest_entries):
            errors.append(f"bundle_manifest_missing_artifact_entry:{relative_path}")

        for relative_path in sorted(expected_paths):
            artifact_path = directory / relative_path
            if not artifact_path.exists():
                errors.append(f"missing_required_artifact:{relative_path}")

        recorded_hashes = {item.relative_path: item for item in manifest.artifact_files}
        for relative_path, record in recorded_hashes.items():
            artifact_path = directory / relative_path
            if not artifact_path.exists():
                errors.append(f"missing_hashed_artifact:{relative_path}")
                continue
            current_hash = self._sha256(artifact_path)
            if current_hash != record.sha256:
                errors.append(f"hash_mismatch:{relative_path}")

        return S23PaperReplayBundleValidationResult(
            is_valid=not errors,
            errors=tuple(errors),
            warnings=tuple(warnings),
            manifest=manifest,
            terminal_state=decision_state or manifest.terminal_state,
            terminal_reason_code=decision_terminal_reason or manifest.terminal_reason_code,
        )

    def summarize_bundle(
        self,
        bundle_directory: str | Path,
    ) -> S23PaperReplayBundleSummary:
        validation = self.validate_bundle(bundle_directory)
        directory = Path(bundle_directory)

        decision_summary = {}
        if (directory / "decision_summary.json").exists():
            decision_summary = self._load_json(directory / "decision_summary.json")

        transitions: list[str] = []
        audit_path = directory / "audit_events.jsonl"
        if audit_path.exists():
            for row in self._load_jsonl(audit_path):
                transitions.append(
                    f"{row.get('previous_state')}->{row.get('new_state')}:{row.get('reason')}"
                )

        return S23PaperReplayBundleSummary(
            bundle_valid=validation.is_valid,
            session_id=self._optional_text(decision_summary.get("session_id")),
            strategy_code=self._optional_text(decision_summary.get("strategy_code")),
            terminal_state=validation.terminal_state,
            terminal_reason_code=validation.terminal_reason_code,
            audit_transition_count=len(transitions),
            audit_transitions=tuple(transitions),
            validation_errors=validation.errors,
            validation_warnings=validation.warnings,
        )

    def _required_artifacts_for_directory(
        self,
        bundle_directory: Path,
        *,
        terminal_state: PaperSessionState,
        selected_contract_required: bool,
    ) -> set[str]:
        expected_paths = self._required_artifacts_for_state(
            terminal_state,
            selected_contract_required=selected_contract_required,
        )
        return expected_paths

    def _required_artifacts_for_state(
        self,
        terminal_state: PaperSessionState,
        *,
        selected_contract_required: bool,
    ) -> set[str]:
        expected_paths = set(_SHARED_ARTIFACTS)
        expected_paths.add(_TERMINAL_ARTIFACTS[terminal_state])
        if selected_contract_required:
            expected_paths.add("selected_contract.json")
        return expected_paths

    def _file_record(
        self,
        bundle_directory: Path,
        relative_path: str,
    ) -> S23PaperReplayBundleFile:
        artifact_path = bundle_directory / relative_path
        return S23PaperReplayBundleFile(
            relative_path=relative_path,
            sha256=self._sha256(artifact_path),
            size_bytes=artifact_path.stat().st_size,
        )

    def _derive_source_root(self, bundle_directory: Path) -> Path:
        if len(bundle_directory.parts) >= 2:
            return bundle_directory.parent.parent
        return bundle_directory.parent

    def _load_bundle_manifest(self, path: Path) -> S23PaperReplayBundleManifest:
        payload = self._load_json(path)
        artifact_files = tuple(
            S23PaperReplayBundleFile(
                relative_path=str(item["relative_path"]),
                sha256=str(item["sha256"]),
                size_bytes=int(item["size_bytes"]),
            )
            for item in payload.get("artifact_files", [])
        )
        return S23PaperReplayBundleManifest(
            bundle_version=int(payload["bundle_version"]),
            created_at=self._parse_datetime(payload["created_at"]),
            strategy_code=str(payload["strategy_code"]),
            session_id=str(payload["session_id"]),
            session_date=self._parse_date(payload["session_date"]),
            terminal_state=PaperSessionState(str(payload["terminal_state"])),
            terminal_reason_code=self._optional_text(payload.get("terminal_reason_code")),
            source_artifact_root=str(payload["source_artifact_root"]),
            source_session_directory=str(payload["source_session_directory"]),
            artifact_files=artifact_files,
        )

    def _load_json(self, path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _load_jsonl(self, path: Path) -> tuple[dict[str, Any], ...]:
        rows: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
        return tuple(rows)

    def _parse_state(self, value: Any) -> PaperSessionState | None:
        if value is None:
            return None
        try:
            return PaperSessionState(str(value))
        except ValueError:
            return None

    def _parse_datetime(self, value: Any) -> datetime:
        return datetime.fromisoformat(str(value))

    def _parse_date(self, value: Any) -> date:
        return date.fromisoformat(str(value))

    def _optional_text(self, value: Any) -> str | None:
        if value is None:
            return None
        rendered = str(value)
        return rendered if rendered else None

    def _sha256(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _write_json(self, path: Path, payload: Any) -> None:
        rendered = json.dumps(
            self._normalize(payload),
            indent=2,
            sort_keys=True,
        ) + "\n"
        path.write_text(rendered, encoding="utf-8", newline="\n")

    def _normalize(self, value: Any) -> Any:
        if is_dataclass(value):
            return {
                field.name: self._normalize(getattr(value, field.name))
                for field in fields(value)
            }
        if isinstance(value, dict):
            return {
                str(key): self._normalize(value[key])
                for key in sorted(value, key=lambda item: str(item))
            }
        if isinstance(value, tuple | list):
            return [self._normalize(item) for item in value]
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, date | time):
            return value.isoformat()
        if isinstance(value, Path):
            return str(value)
        return value
