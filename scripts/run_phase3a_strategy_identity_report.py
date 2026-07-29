from __future__ import annotations

import json
from pathlib import Path
import sys
from time import perf_counter
import tracemalloc


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tfis.domain import load_strategy_configuration_resolver  # noqa: E402


def main() -> int:
    tracemalloc.start()
    start = perf_counter()
    resolver = load_strategy_configuration_resolver(REPO_ROOT)
    load_and_validation_seconds = perf_counter() - start
    current, peak = tracemalloc.get_traced_memory()
    start = perf_counter()
    s23 = resolver.resolve("S23_NIFTY_ACCOUNT_A_PAPER")
    single_resolution_seconds = perf_counter() - start
    start = perf_counter()
    resolver.resolve("S23_NIFTY_ACCOUNT_A_PAPER")
    cached_resolution_seconds = perf_counter() - start
    s21 = resolver.resolve("S21_BANKNIFTY_ACCOUNT_A_PAPER")
    report = {
        "load_and_validation_seconds": load_and_validation_seconds,
        "single_resolution_seconds": single_resolution_seconds,
        "cached_resolution_seconds": cached_resolution_seconds,
        "memory_current_bytes": current,
        "memory_peak_bytes": peak,
        "families": len(resolver.families),
        "definitions": len(resolver.definitions),
        "versions": len(resolver.versions),
        "instances": len(resolver.instances),
        "resolved_examples": [
            {
                "strategy_instance_id": s23.instance.strategy_instance_id,
                "strategy_definition_id": s23.definition.strategy_definition_id,
                "strategy_version": s23.version.strategy_version,
                "entry_policy": s23.resolved_policy_keys.entry_policy,
                "configuration_hash": s23.effective_configuration_hash,
            },
            {
                "strategy_instance_id": s21.instance.strategy_instance_id,
                "strategy_definition_id": s21.definition.strategy_definition_id,
                "strategy_version": s21.version.strategy_version,
                "entry_policy": s21.resolved_policy_keys.entry_policy,
                "configuration_hash": s21.effective_configuration_hash,
            },
        ],
    }
    output_dir = REPO_ROOT / "reports" / "phase3a"
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "strategy_identity_report.json"
    md_path = output_dir / "strategy_identity_summary.md"
    json_path.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(_markdown(report), encoding="utf-8")
    print(f"json: {json_path}")
    print(f"markdown: {md_path}")
    return 0


def _markdown(report: dict[str, object]) -> str:
    lines = [
        "# Phase 3A Strategy Identity Report",
        "",
        f"- families: {report['families']}",
        f"- definitions: {report['definitions']}",
        f"- versions: {report['versions']}",
        f"- instances: {report['instances']}",
        f"- load_and_validation_seconds: {report['load_and_validation_seconds']}",
        f"- single_resolution_seconds: {report['single_resolution_seconds']}",
        f"- cached_resolution_seconds: {report['cached_resolution_seconds']}",
        f"- memory_current_bytes: {report['memory_current_bytes']}",
        f"- memory_peak_bytes: {report['memory_peak_bytes']}",
        "",
        "## Resolved Examples",
        "",
    ]
    for item in report["resolved_examples"]:
        lines.append(f"- {item['strategy_instance_id']}: {item['strategy_definition_id']}@{item['strategy_version']} {item['entry_policy']} {item['configuration_hash'][:12]}")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
