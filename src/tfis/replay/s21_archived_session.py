from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Iterable


class S21ArchivedSessionError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class S21ArchivedCheckpoint:
    label: str
    directory: Path | None
    option_chain_snapshot: Path | None
    underlying_bars: Path | None
    underlying_daily_bars: Path | None
    underlying_snapshot: Path | None
    preflight_summary: Path | None

    @property
    def market_evidence_ready(self) -> bool:
        return bool(
            self.directory
            and self.option_chain_snapshot
            and self.underlying_daily_bars
        )


@dataclass(frozen=True, slots=True)
class S21ArchivedBranchArtifacts:
    branch: str
    directory: Path
    monthly_status_0916: Path | None
    monthly_status_0925: Path | None
    monthly_status_0930: Path | None
    trade_decision_explainer: Path | None
    trade_decision_summary: Path | None
    paper_order_state: Path | None
    paper_order_events: Path | None
    selected_contract_market_events: Path | None


@dataclass(frozen=True, slots=True)
class S21ArchivedSession:
    session_date: date
    source_date_root: Path
    checkpoint_0916: S21ArchivedCheckpoint
    checkpoint_0925: S21ArchivedCheckpoint
    checkpoint_0930: S21ArchivedCheckpoint
    final_session_directory: Path | None
    scheduled_run_metadata: Path | None
    branches: tuple[S21ArchivedBranchArtifacts, ...]

    @property
    def replay_market_evidence_ready(self) -> bool:
        return self.checkpoint_0916.market_evidence_ready

    @property
    def has_original_decision_evidence(self) -> bool:
        return any(
            b.trade_decision_explainer is not None
            or b.trade_decision_summary is not None
            for b in self.branches
        )

    @property
    def has_persisted_selected_contract_events(self) -> bool:
        return any(b.selected_contract_market_events is not None for b in self.branches)

    def to_index_payload(self) -> dict:
        def p(value: Path | None):
            return str(value) if value is not None else None

        return {
            "session_date": self.session_date.isoformat(),
            "source_date_root": str(self.source_date_root),
            "replay_market_evidence_ready": self.replay_market_evidence_ready,
            "has_original_decision_evidence": self.has_original_decision_evidence,
            "has_persisted_selected_contract_events": self.has_persisted_selected_contract_events,
            "checkpoints": {
                cp.label: {
                    "directory": p(cp.directory),
                    "option_chain_snapshot": p(cp.option_chain_snapshot),
                    "underlying_bars": p(cp.underlying_bars),
                    "underlying_daily_bars": p(cp.underlying_daily_bars),
                    "underlying_snapshot": p(cp.underlying_snapshot),
                    "preflight_summary": p(cp.preflight_summary),
                    "market_evidence_ready": cp.market_evidence_ready,
                }
                for cp in (
                    self.checkpoint_0916,
                    self.checkpoint_0925,
                    self.checkpoint_0930,
                )
            },
            "final_session_directory": p(self.final_session_directory),
            "scheduled_run_metadata": p(self.scheduled_run_metadata),
            "branches": [
                {
                    "branch": b.branch,
                    "directory": str(b.directory),
                    "monthly_status_0916": p(b.monthly_status_0916),
                    "monthly_status_0925": p(b.monthly_status_0925),
                    "monthly_status_0930": p(b.monthly_status_0930),
                    "trade_decision_explainer": p(b.trade_decision_explainer),
                    "trade_decision_summary": p(b.trade_decision_summary),
                    "paper_order_state": p(b.paper_order_state),
                    "paper_order_events": p(b.paper_order_events),
                    "selected_contract_market_events": p(
                        b.selected_contract_market_events
                    ),
                }
                for b in self.branches
            ],
        }


class S21ArchivedStrategySessionAdapter:
    """Read-only adapter over durable S21 strategy-session artifacts.

    The adapter never calls a broker and never mutates the source tree.
    It exposes the durable runtime artifact layout as replay/certification input.

    Existing replay code currently expects:
        <certification-root>/<date>/archived_runtime_evidence/...

    `materialize_compatibility_view()` creates a directory junction/symlink
    pointing at the original durable day directory, avoiding a second copy of
    the evidence while allowing the existing builder to remain unchanged.
    """

    def __init__(
        self,
        source_root: str | Path = (
            "data/strategies/S21/fyers_morning_supervised_decision"
        ),
    ) -> None:
        self.source_root = Path(source_root)

    def discover_dates(self) -> tuple[date, ...]:
        if not self.source_root.exists():
            return ()
        result: list[date] = []
        for candidate in self.source_root.iterdir():
            if not candidate.is_dir():
                continue
            try:
                parsed = date.fromisoformat(candidate.name)
            except ValueError:
                continue
            result.append(parsed)
        return tuple(sorted(result))

    def load(self, session_date: date) -> S21ArchivedSession:
        root = self.source_root / session_date.isoformat()
        if not root.exists():
            raise S21ArchivedSessionError(
                f"Missing S21 archived strategy session: {root}"
            )

        dirs = tuple(p for p in root.iterdir() if p.is_dir())
        cp0916 = self._checkpoint(dirs, "0916")
        cp0925 = self._checkpoint(dirs, "0925")
        cp0930 = self._checkpoint(dirs, "0930")

        final_dirs = tuple(
            p
            for p in dirs
            if not any(label in p.name for label in ("0916", "0925", "0930"))
        )
        final_dir = self._select_final_session_directory(final_dirs, session_date)

        branches: list[S21ArchivedBranchArtifacts] = []
        scheduled = None
        if final_dir is not None:
            scheduled = self._existing(final_dir / "scheduled_run_metadata.json")
            for branch_dir in sorted(
                (p for p in final_dir.iterdir() if p.is_dir()),
                key=lambda p: p.name,
            ):
                branches.append(
                    S21ArchivedBranchArtifacts(
                        branch=branch_dir.name,
                        directory=branch_dir,
                        monthly_status_0916=self._existing(
                            branch_dir / "monthly_status_stage_0916.json"
                        ),
                        monthly_status_0925=self._existing(
                            branch_dir / "monthly_status_stage_0925.json"
                        ),
                        monthly_status_0930=self._existing(
                            branch_dir / "monthly_status_stage_0930.json"
                        ),
                        trade_decision_explainer=self._existing(
                            branch_dir / "trade_decision_explainer.json"
                        ),
                        trade_decision_summary=self._existing(
                            branch_dir / "trade_decision_summary.json"
                        ),
                        paper_order_state=self._existing(
                            branch_dir / "paper_order_state.json"
                        ),
                        paper_order_events=self._existing(
                            branch_dir / "paper_order_events.jsonl"
                        ),
                        selected_contract_market_events=self._existing(
                            branch_dir / "selected_contract_market_events.jsonl"
                        ),
                    )
                )

        return S21ArchivedSession(
            session_date=session_date,
            source_date_root=root,
            checkpoint_0916=cp0916,
            checkpoint_0925=cp0925,
            checkpoint_0930=cp0930,
            final_session_directory=final_dir,
            scheduled_run_metadata=scheduled,
            branches=tuple(branches),
        )

    def build_index(self) -> tuple[S21ArchivedSession, ...]:
        return tuple(self.load(d) for d in self.discover_dates())

    def write_index(self, output_path: str | Path) -> Path:
        sessions = self.build_index()
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(
                {
                    "source_root": str(self.source_root),
                    "session_count": len(sessions),
                    "sessions": [x.to_index_payload() for x in sessions],
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        return output

    def materialize_compatibility_view(
        self,
        *,
        session_date: date,
        compatibility_root: str | Path,
        replace_existing: bool = False,
    ) -> Path:
        session = self.load(session_date)
        day_root = Path(compatibility_root) / session_date.isoformat()
        link = day_root / "archived_runtime_evidence"

        if link.exists() or link.is_symlink():
            if self._same_target(link, session.source_date_root):
                return link
            if not replace_existing:
                raise S21ArchivedSessionError(
                    f"Compatibility view already exists with another target: {link}"
                )
            self._remove_link_or_tree(link)

        day_root.mkdir(parents=True, exist_ok=True)
        self._create_directory_link(
            link=link,
            target=session.source_date_root.resolve(),
        )
        return link

    def materialize_all_compatibility_views(
        self,
        *,
        compatibility_root: str | Path,
        replace_existing: bool = False,
    ) -> tuple[Path, ...]:
        return tuple(
            self.materialize_compatibility_view(
                session_date=d,
                compatibility_root=compatibility_root,
                replace_existing=replace_existing,
            )
            for d in self.discover_dates()
        )

    @staticmethod
    def _existing(path: Path) -> Path | None:
        return path if path.exists() else None

    def _checkpoint(
        self,
        directories: Iterable[Path],
        label: str,
    ) -> S21ArchivedCheckpoint:
        matches = sorted(
            (p for p in directories if label in p.name),
            key=lambda p: p.name,
        )
        directory = matches[0] if matches else None
        return S21ArchivedCheckpoint(
            label=label,
            directory=directory,
            option_chain_snapshot=(
                self._existing(directory / "normalized_option_chain_snapshot.json")
                if directory else None
            ),
            underlying_bars=(
                self._existing(directory / "normalized_underlying_bars.json")
                if directory else None
            ),
            underlying_daily_bars=(
                self._existing(directory / "normalized_underlying_daily_bars.json")
                if directory else None
            ),
            underlying_snapshot=(
                self._existing(directory / "normalized_underlying_snapshot.json")
                if directory else None
            ),
            preflight_summary=(
                self._existing(directory / "snapshot_preflight_summary.json")
                if directory else None
            ),
        )

    @staticmethod
    def _select_final_session_directory(
        candidates: tuple[Path, ...],
        session_date: date,
    ) -> Path | None:
        if not candidates:
            return None
        exact_suffix = f"-{session_date.isoformat()}"
        preferred = tuple(
            p for p in candidates if p.name.endswith(exact_suffix)
        )
        pool = preferred or candidates
        return sorted(pool, key=lambda p: p.name)[0]

    @staticmethod
    def _same_target(link: Path, target: Path) -> bool:
        try:
            return link.resolve() == target.resolve()
        except OSError:
            return False

    @staticmethod
    def _remove_link_or_tree(path: Path) -> None:
        # Directory junctions must be removed as links, never recursively
        # deleting their target.
        if path.is_symlink():
            path.unlink()
            return
        if os.name == "nt":
            proc = subprocess.run(
                ["cmd", "/c", "rmdir", str(path)],
                capture_output=True,
                text=True,
            )
            if proc.returncode == 0:
                return
        if path.exists():
            raise S21ArchivedSessionError(
                "Refusing to recursively delete an existing non-link directory: "
                f"{path}"
            )

    @staticmethod
    def _create_directory_link(*, link: Path, target: Path) -> None:
        if os.name == "nt":
            # Junction creation does not require Developer Mode/admin and is
            # appropriate because source + compatibility root are local dirs.
            proc = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(link), str(target)],
                capture_output=True,
                text=True,
            )
            if proc.returncode != 0:
                raise S21ArchivedSessionError(
                    f"Unable to create Windows directory junction {link} -> {target}: "
                    f"{proc.stdout} {proc.stderr}".strip()
                )
            return

        try:
            link.symlink_to(target, target_is_directory=True)
        except OSError as exc:
            raise S21ArchivedSessionError(
                f"Unable to create directory symlink {link} -> {target}: {exc}"
            ) from exc
