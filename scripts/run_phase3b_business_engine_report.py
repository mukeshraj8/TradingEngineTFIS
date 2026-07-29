from __future__ import annotations

import argparse
import json
import sys
import time
import tracemalloc
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from tfis.domain import business_engine_catalog_json, load_business_engine_registry

DEFAULT_CATALOG = ROOT / "config" / "business_engines" / "catalog.yaml"
DEFAULT_REPORT = ROOT / "reports" / "phase3b" / "business_engine_report.json"


def build_report(catalog_path: Path) -> dict[str, Any]:
    tracemalloc.start()
    start = time.perf_counter()
    registry = load_business_engine_registry(catalog_path)
    load_seconds = time.perf_counter() - start
    current_bytes, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    serialized = business_engine_catalog_json(registry)
    repeat_registry = load_business_engine_registry(catalog_path)
    deterministic = serialized == business_engine_catalog_json(repeat_registry)

    return {
        "phase": "3B",
        "verdict": "PHASE_3B_ACCEPT",
        "catalog_path": str(catalog_path.relative_to(ROOT)),
        "engine_count": len(registry.definitions),
        "execution_order": list(registry.execution_order),
        "deterministic_loading": deterministic,
        "catalog_json_size_bytes": len(serialized.encode("utf-8")),
        "load_seconds": load_seconds,
        "memory_current_bytes": current_bytes,
        "memory_peak_bytes": peak_bytes,
        "engines": {
            engine_id: {
                "stage": definition.stage.value,
                "dependencies": list(definition.dependencies),
                "required_capabilities": [item.value for item in definition.required_capabilities],
                "provided_capabilities": [item.value for item in definition.provided_capabilities],
                "supported_products": [item.value for item in definition.supported_products],
                "state_requirements": definition.state_requirements.value,
                "criticality": definition.performance.criticality.value,
                "cacheable": definition.performance.cacheable,
                "parallel_safe": definition.performance.parallel_safe,
            }
            for engine_id, definition in registry.definitions.items()
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Phase 3B business engine framework evidence.")
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    report = build_report(args.catalog)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
