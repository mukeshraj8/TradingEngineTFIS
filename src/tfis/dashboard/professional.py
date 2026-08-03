from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


FRONTEND_ROOT = Path("dashboard/frontend")


@dataclass(frozen=True, slots=True)
class ProfessionalDashboardBuildResult:
    output_root: Path
    index_html: Path
    snapshot_json: Path
    manifest_json: Path

    def to_dict(self) -> dict[str, str]:
        return {
            "output_root": str(self.output_root),
            "index_html": str(self.index_html),
            "snapshot_json": str(self.snapshot_json),
            "manifest_json": str(self.manifest_json),
        }


def build_professional_dashboard(
    projection: Mapping[str, Any],
    *,
    output_root: str | Path = "tmp/tfis_dashboard_v1",
    frontend_root: str | Path = FRONTEND_ROOT,
) -> ProfessionalDashboardBuildResult:
    target = Path(output_root)
    target.mkdir(parents=True, exist_ok=True)
    source = Path(frontend_root)
    for name in ("index.html", "styles.css", "app.js"):
        shutil.copyfile(source / name, target / name)
    api_dir = target / "api"
    api_dir.mkdir(exist_ok=True)
    snapshot = api_dir / "snapshot.json"
    snapshot.write_text(json.dumps(projection, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest = target / "dashboard_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "dashboard": "TFIS Professional Operations Dashboard",
                "projection_hash": projection["projection_hash"],
                "snapshot": "api/snapshot.json",
                "broker_order_authority": projection["system"]["broker_order_authority"],
                "frontend_formula_calculation": False,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return ProfessionalDashboardBuildResult(
        output_root=target,
        index_html=target / "index.html",
        snapshot_json=snapshot,
        manifest_json=manifest,
    )
