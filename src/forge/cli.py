from __future__ import annotations

import argparse
from pathlib import Path
import sys

from forge.runner import RunOnceRequest, run_once


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="forge")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run-once")
    run_parser.add_argument("task")
    run_parser.add_argument("--condition", choices=["baseline", "skill"], required=True)
    run_parser.add_argument("--trial", type=int, required=True)
    run_parser.add_argument("--seed", type=int, required=True)
    run_parser.add_argument("--experiment-id", required=True)
    run_parser.add_argument("--db", required=True)
    run_parser.add_argument("--skill")
    run_parser.add_argument("--agent-cmd", nargs="+", required=True)

    args = parser.parse_args(argv)
    if args.command == "run-once":
        result = run_once(
            RunOnceRequest(
                task_path=Path(args.task),
                condition=args.condition,
                trial=args.trial,
                seed=args.seed,
                experiment_id=args.experiment_id,
                db_path=Path(args.db),
                agent_cmd=args.agent_cmd,
                skill_path=Path(args.skill) if args.skill is not None else None,
            )
        )
        print(f"{result.run_id} {result.status}")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
