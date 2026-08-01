from __future__ import annotations

import argparse
import json

from tfis.internal_paper.runtime import ControlledInternalPaperRuntime, OperatorCommand, OperatorCommandType


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the controlled S23 internal-paper single-instance profile.")
    parser.add_argument("--profile", default="internal_paper_s23_single_instance")
    parser.add_argument("--session", default="PHASE5A_CERTIFICATION_FIXTURE")
    parser.add_argument("--enable-internal-paper", action="store_true")
    parser.add_argument("--scenario", default="bull_target")
    parser.add_argument("--operator", default="LOCAL_OPERATOR")
    args = parser.parse_args()

    runtime = ControlledInternalPaperRuntime()
    if args.profile != runtime.profile.profile_id:
        raise SystemExit(f"Unsupported profile: {args.profile}")
    if args.enable_internal_paper:
        commands = (
            OperatorCommand(
                command_type=OperatorCommandType.ENABLE_INTERNAL_PAPER,
                operator_reference=args.operator,
                timestamp=__import__("datetime").datetime.fromisoformat("2026-06-05T09:00:00+05:30"),
                reason=f"Explicit controlled activation for {args.session}.",
            ),
        )
        result = runtime.run(scenario_id=args.scenario, commands=commands)
    else:
        result = runtime.preview(operator_reference=args.operator)
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
