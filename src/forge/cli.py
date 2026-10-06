from __future__ import annotations

import argparse
from pathlib import Path
import sys

from forge.runner import RunOnceRequest, run_once
from forge.validation import validate_task


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
    run_parser.add_argument("--skill-id")
    agent_group = run_parser.add_mutually_exclusive_group(required=True)
    agent_group.add_argument("--agent-cmd", nargs="+")
    agent_group.add_argument("--agent", choices=["codex"])
    run_parser.add_argument("--model")
    run_parser.add_argument("--reasoning-effort")
    run_parser.add_argument("--codex-bin", default="codex")
    run_parser.add_argument("--codex-auth")
    validate_parser = subparsers.add_parser("validate-task")
    validate_parser.add_argument("task")
    validate_parser.add_argument("--db", required=True)
    validate_parser.add_argument("--repeats", type=int, default=3)

    args = parser.parse_args(argv)
    if args.command == "validate-task":
        ok, message = validate_task(Path(args.task), Path(args.db), args.repeats)
        print(f"{message} {args.task}")
        return 0 if ok else 1
    if args.command == "run-once":
        result = run_once(
            RunOnceRequest(
                task_path=Path(args.task),
                condition=args.condition,
                trial=args.trial,
                seed=args.seed,
                experiment_id=args.experiment_id,
                db_path=Path(args.db),
                agent_cmd=args.agent_cmd or [],
                skill_path=Path(args.skill) if args.skill is not None else None,
                skill_id=args.skill_id,
                agent=args.agent,
                model=args.model,
                reasoning_effort=args.reasoning_effort,
                codex_bin=args.codex_bin,
                codex_auth=Path(args.codex_auth) if args.codex_auth is not None else None,
            )
        )
        print(f"{result.run_id} {result.status}")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
