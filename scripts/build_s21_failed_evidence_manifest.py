from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    payload = json.loads(Path(args.summary).read_text(encoding="utf-8"))
    symbols = sorted(
        {
            str(row["symbol"])
            for row in payload.get("failures", [])
            if row.get("symbol")
        }
    )
    Path(args.output).write_text(
        ("\n".join(symbols) + "\n") if symbols else "",
        encoding="utf-8",
    )
    print(f"Failed-symbol manifest: {args.output}")
    print(f"Symbols: {len(symbols)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
