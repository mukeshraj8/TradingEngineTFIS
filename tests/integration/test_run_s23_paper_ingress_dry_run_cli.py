from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "paper"
    / "s23_archive_ingress_dry_run.jsonl"
)


def test_run_s23_paper_ingress_dry_run_cli_writes_outputs(tmp_path: Path) -> None:
    script_path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "run_s23_paper_ingress_dry_run.py"
    )
    out_json = tmp_path / "dry_run.json"
    out_md = tmp_path / "dry_run.md"
    artifact_root = tmp_path / "dry_runs"

    completed = subprocess.run(
        [
            sys.executable,
            str(script_path),
            "--events-jsonl",
            str(FIXTURE_PATH),
            "--artifact-root",
            str(artifact_root),
            "--session-id",
            "cli-ingress-dry-run",
            "--out-json",
            str(out_json),
            "--out-md",
            str(out_md),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert out_json.exists()
    assert out_md.exists()

    payload = json.loads(out_json.read_text(encoding="utf-8"))
    markdown = out_md.read_text(encoding="utf-8")

    assert payload["terminal_state"] == "ORDER_PLANNED"
    assert payload["operational_readiness"] == "PASS"
    assert payload["source_mode"] == "normalized_archive_export_jsonl"
    assert "ORDER_PLANNED" in markdown
    assert "No broker API was used." in markdown
