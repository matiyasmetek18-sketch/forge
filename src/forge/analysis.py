from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
import math
from pathlib import Path
import random
import sqlite3
from statistics import fmean, median
import tomllib
import uuid

from forge import __version__
from forge.db import _ensure_schema, insert_analysis
from forge.task import InvalidConfigError


PILOT_WARNING = "PILOT (development data): NOT EVIDENCE"
DEFAULT_RULE_TOML = (
    'rule_version = "v1"\n'
    "min_effect_pp = 3.0\n"
    "max_token_increase_pct = 25.0\n"
    "max_task_drop_pp = 40.0\n"
    "max_crash_rate_pct = 5.0\n"
    "min_tasks = 10\n"
    "min_trials_per_condition = 3\n"
)
KNOWN_STATUSES = {
    "passed", "failed", "agent_error", "agent_timeout", "grader_error",
    "infra_error", "invalid_config",
}


class AnalysisMismatchError(Exception):
    """Stored final evidence differs from recomputation."""


@dataclass(frozen=True)
class Rule:
    sha256: str
    rule_version: str
    min_effect_pp: float
    max_token_increase_pct: float
    max_task_drop_pp: float
    max_crash_rate_pct: float
    min_tasks: int
    min_trials_per_condition: int


def analysis_code_sha256() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def load_rule(path: Path | None) -> Rule:
    try:
        raw = path.read_bytes() if path is not None else DEFAULT_RULE_TOML.encode("utf-8")
        data = tomllib.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise InvalidConfigError("cannot read valid UTF-8 rule TOML") from exc
    defaults = tomllib.loads(DEFAULT_RULE_TOML)
    unknown = set(data) - set(defaults)
    if unknown:
        raise InvalidConfigError("unknown rule fields: " + ", ".join(sorted(unknown)))
    merged = defaults | data
    if merged["rule_version"] != "v1":
        raise InvalidConfigError("unsupported rule_version")
    for key in ("min_effect_pp", "max_token_increase_pct", "max_task_drop_pp", "max_crash_rate_pct"):
        value = merged[key]
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise InvalidConfigError(f"{key} must be a finite nonnegative number")
    if merged["max_task_drop_pp"] > 100 or merged["max_crash_rate_pct"] > 100:
        raise InvalidConfigError("percentage guardrails must not exceed 100")
    for key in ("min_tasks", "min_trials_per_condition"):
        if type(merged[key]) is not int or merged[key] < 1:
            raise InvalidConfigError(f"{key} must be a positive integer")
    return Rule(
        hashlib.sha256(raw).hexdigest(), merged["rule_version"],
        float(merged["min_effect_pp"]), float(merged["max_token_increase_pct"]),
        float(merged["max_task_drop_pp"]), float(merged["max_crash_rate_pct"]),
        merged["min_tasks"], merged["min_trials_per_condition"],
    )


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _token_total(row: sqlite3.Row) -> int | None:
    if row["input_tokens"] is None or row["output_tokens"] is None:
        return None
    return row["input_tokens"] + row["output_tokens"]


def _telemetry(rows: list[sqlite3.Row]) -> dict[str, float | int | None]:
    tokens = [_token_total(row) for row in rows]
    wall = [row["wall_seconds"] for row in rows]
    commands = [row["command_count"] for row in rows]
    return {
        "median_tokens": median(value for value in tokens if value is not None) if any(value is not None for value in tokens) else None,
        "median_wall_seconds": median(value for value in wall if value is not None) if any(value is not None for value in wall) else None,
        "median_command_count": median(value for value in commands if value is not None) if any(value is not None for value in commands) else None,
        "missing_tokens": sum(value is None for value in tokens),
        "missing_wall_seconds": sum(value is None for value in wall),
        "missing_command_count": sum(value is None for value in commands),
        "runs": len(rows),
    }


def _relative_tokens(baseline: float | None, skill: float | None) -> tuple[float | None, str | None]:
    if baseline is None or skill is None:
        return None, "missing_token_median"
    if baseline == 0:
        return None, "baseline_median_zero"
    return (skill - baseline) / baseline * 100, None


def _bootstrap(
    task_deltas: list[float], token_by_task: dict[str, dict[str, list[int]]],
    task_ids: list[str], samples: int, seed: int,
) -> tuple[float | None, float | None, float | None, float | None, int]:
    rng = random.Random(seed)
    primary: list[float] = []
    if task_deltas:
        for _ in range(samples):
            primary.append(fmean(rng.choice(task_deltas) for _ in task_deltas) * 100)
    token_changes: list[float] = []
    if task_ids:
        for _ in range(samples):
            sampled = [rng.choice(task_ids) for _ in task_ids]
            baseline = [token for task in sampled for token in token_by_task[task]["baseline"]]
            skill = [token for task in sampled for token in token_by_task[task]["skill"]]
            relative, _ = _relative_tokens(median(baseline) if baseline else None, median(skill) if skill else None)
            if relative is not None:
                token_changes.append(relative)
    return (
        _percentile(primary, 0.025) if primary else None,
        _percentile(primary, 0.975) if primary else None,
        _percentile(token_changes, 0.025) if token_changes else None,
        _percentile(token_changes, 0.975) if token_changes else None,
        len(token_changes),
    )


def _read_data(db_path: Path, experiment_id: str):
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        _ensure_schema(conn)
        experiment = conn.execute("SELECT * FROM experiments WHERE experiment_id=?", (experiment_id,)).fetchone()
        if experiment is None:
            raise InvalidConfigError(f"experiment not found: {experiment_id}")
        planned = conn.execute(
            """
            SELECT p.task_id, p.condition, p.trial, p.run_id, p.attempts,
                   r.status, r.input_tokens, r.output_tokens, r.wall_seconds, r.command_count
            FROM experiment_runs AS p
            LEFT JOIN runs AS r ON r.run_id=p.run_id AND r.experiment_id=p.experiment_id
            WHERE p.experiment_id=? ORDER BY p.planned_position
            """,
            (experiment_id,),
        ).fetchall()
        if not planned:
            raise InvalidConfigError("experiment has no planned runs")
        attempts = conn.execute("SELECT run_id, status FROM runs WHERE experiment_id=?", (experiment_id,)).fetchall()
        stored = conn.execute(
            "SELECT * FROM analyses WHERE experiment_id=? AND phase='final' LIMIT 1", (experiment_id,)
        ).fetchone()
        freezes = conn.execute(
            "SELECT * FROM freezes WHERE manifest_sha256=? AND benchmark_hash=? AND skill_sha256 IS ?",
            (experiment["manifest_sha256"], experiment["benchmark_hash"], experiment["skill_sha256"]),
        ).fetchall()
    return experiment, planned, attempts, stored, freezes


def _compute_report(
    experiment: sqlite3.Row, planned: list[sqlite3.Row], attempts: list[sqlite3.Row],
    rule: Rule, samples: int, seed: int, code_sha: str,
) -> dict[str, object]:
    by_task: dict[str, dict[str, list[sqlite3.Row]]] = defaultdict(lambda: {"baseline": [], "skill": []})
    by_condition: dict[str, list[sqlite3.Row]] = {"baseline": [], "skill": []}
    status_counts: dict[str, Counter[str]] = {"baseline": Counter(), "skill": Counter()}
    final_infra = Counter()
    pending = 0
    linked_ids = set()
    for row in planned:
        condition = row["condition"]
        if condition not in by_condition:
            raise InvalidConfigError(f"unknown planned condition: {condition}")
        by_task[row["task_id"]][condition].append(row)
        if row["run_id"] is None:
            pending += 1
            continue
        if row["status"] is None:
            raise InvalidConfigError("planned run links to a missing record")
        if row["status"] not in KNOWN_STATUSES:
            raise InvalidConfigError(f"unknown run status: {row['status']}")
        linked_ids.add(row["run_id"])
        by_condition[condition].append(row)
        status_counts[condition][row["status"]] += 1
        if row["status"] == "infra_error":
            if row["attempts"] >= 2:
                final_infra[condition] += 1
            else:
                pending += 1

    task_rows: list[dict[str, object]] = []
    dropped: list[str] = []
    deltas: list[float] = []
    for task_id in sorted(by_task):
        baseline = [row for row in by_task[task_id]["baseline"] if row["status"] is not None and row["status"] != "infra_error"]
        skill = [row for row in by_task[task_id]["skill"] if row["status"] is not None and row["status"] != "infra_error"]
        if not baseline or not skill:
            dropped.append(task_id)
            continue
        base_rate = sum(row["status"] == "passed" for row in baseline) / len(baseline)
        skill_rate = sum(row["status"] == "passed" for row in skill) / len(skill)
        delta = skill_rate - base_rate
        deltas.append(delta)
        task_rows.append({
            "task_id": task_id, "baseline_rate": base_rate, "skill_rate": skill_rate,
            "delta_pp": delta * 100, "baseline_valid": len(baseline), "skill_valid": len(skill),
        })

    estimate = fmean(deltas) * 100 if deltas else None
    telemetry = {condition: _telemetry(rows) for condition, rows in by_condition.items()}
    relative, undefined_reason = _relative_tokens(
        telemetry["baseline"]["median_tokens"], telemetry["skill"]["median_tokens"],
    )
    token_by_task = {
        task_id: {
            condition: [total for row in entries[condition] if row["run_id"] is not None if (total := _token_total(row)) is not None]
            for condition in ("baseline", "skill")
        }
        for task_id, entries in by_task.items()
    }
    ci_lo, ci_hi, token_ci_lo, token_ci_hi, token_samples_used = _bootstrap(
        deltas, token_by_task, sorted(by_task), samples, seed,
    )
    telemetry.update({
        "relative_token_change_pct": relative,
        "relative_token_undefined_reason": undefined_reason,
        "relative_token_ci_lo_pct": token_ci_lo,
        "relative_token_ci_hi_pct": token_ci_hi,
        "token_bootstrap_samples_used": token_samples_used,
    })

    health: dict[str, object] = {}
    for condition in ("baseline", "skill"):
        total = sum(row["condition"] == condition for row in planned)
        crashes = sum(status_counts[condition][status] for status in ("agent_error", "agent_timeout", "grader_error"))
        health[condition] = {
            "planned_runs": total, "status_counts": dict(sorted(status_counts[condition].items())),
            "agent_error": status_counts[condition]["agent_error"],
            "agent_timeout": status_counts[condition]["agent_timeout"],
            "grader_error": status_counts[condition]["grader_error"],
            "final_infra_errors": final_infra[condition],
            "crash_rate_pct": crashes / total * 100 if total else None,
            "final_infra_rate_pct": final_infra[condition] / total * 100 if total else None,
        }
    base_health = health["baseline"]
    skill_health = health["skill"]
    health_ok = (
        base_health["crash_rate_pct"] is not None and skill_health["crash_rate_pct"] is not None
        and base_health["crash_rate_pct"] < rule.max_crash_rate_pct
        and skill_health["crash_rate_pct"] < rule.max_crash_rate_pct
        and abs(base_health["final_infra_rate_pct"] - skill_health["final_infra_rate_pct"]) <= rule.max_crash_rate_pct
    )
    health["ok"] = health_ok

    token_ok = relative is None or relative <= rule.max_token_increase_pct
    task_drop_ok = all(row["delta_pp"] >= -rule.max_task_drop_pp for row in task_rows)
    guardrails = {"ok": token_ok and task_drop_ok, "token_ok": token_ok, "task_drop_ok": task_drop_ok}
    enough_tasks = len(task_rows) >= rule.min_tasks
    enough_trials = all(
        row["baseline_valid"] >= rule.min_trials_per_condition
        and row["skill_valid"] >= rule.min_trials_per_condition for row in task_rows
    )
    enough_data = enough_tasks and enough_trials
    reasons: list[str] = []
    if not health_ok:
        reasons.append("health_failure")
    if not enough_tasks:
        reasons.append("insufficient_tasks")
    if not enough_trials:
        reasons.append("insufficient_trials")
    if dropped:
        reasons.append("dropped_tasks")
    if pending:
        reasons.append("incomplete_plan")
    if not token_ok:
        reasons.append("token_guardrail")
    if not task_drop_ok:
        reasons.append("task_drop_guardrail")
    if not health_ok or not enough_data or dropped or pending or ci_lo is None:
        verdict = "INCONCLUSIVE"
    elif ci_lo > rule.min_effect_pp and guardrails["ok"]:
        verdict = "PROMOTE"
        reasons.append("effect_exceeds_threshold")
    elif ci_hi < rule.min_effect_pp or (ci_lo > rule.min_effect_pp and not guardrails["ok"]):
        verdict = "REJECT"
        if ci_hi < rule.min_effect_pp:
            reasons.append("effect_below_threshold")
    else:
        verdict = "INCONCLUSIVE"
    if verdict == "INCONCLUSIVE":
        reasons.append("add tasks or trials; do not rerun until significant")

    unlinked = Counter(row["status"] for row in attempts if row["run_id"] not in linked_ids)
    return {
        "experiment_id": experiment["experiment_id"], "phase": experiment["phase"],
        "phase_warning": PILOT_WARNING if experiment["phase"] == "pilot" else None,
        "rule_sha256": rule.sha256, "rule_version": rule.rule_version,
        "analysis_code_sha256": code_sha, "bootstrap_samples": samples,
        "analysis_seed": seed, "n_tasks": len(task_rows), "tasks": task_rows,
        "dropped_tasks": dropped, "pending_runs": pending,
        "estimate_pp": estimate, "ci_lo_pp": ci_lo, "ci_hi_pp": ci_hi,
        "telemetry": telemetry, "health": health, "guardrails": guardrails,
        "enough_data": enough_data, "unlinked_runs": dict(sorted(unlinked.items())),
        "rule": {
            "min_effect_pp": rule.min_effect_pp,
            "max_token_increase_pct": rule.max_token_increase_pct,
            "max_task_drop_pp": rule.max_task_drop_pp,
            "max_crash_rate_pct": rule.max_crash_rate_pct,
            "min_tasks": rule.min_tasks,
            "min_trials_per_condition": rule.min_trials_per_condition,
        },
        "verdict": verdict, "reasons": reasons,
        "regression_rate_limitation": "Forge V1 does not measure previously-passing tests that subsequently regress.",
    }


def analyze_experiment(
    db_path: Path, experiment_id: str, rule_path: Path | None,
    bootstrap_samples: int = 10000, analysis_seed: int = 12345,
) -> dict[str, object]:
    if bootstrap_samples < 1:
        raise InvalidConfigError("bootstrap_samples must be positive")
    rule = load_rule(rule_path)
    code_sha = analysis_code_sha256()
    experiment, planned, attempts, stored, freezes = _read_data(db_path, experiment_id)
    phase = experiment["phase"]
    if phase not in {"pilot", "final"}:
        raise InvalidConfigError("unknown experiment phase")
    if phase == "final":
        if rule_path is None:
            raise InvalidConfigError("final analysis requires --rule")
        matching = any(
            row["rule_sha256"] == rule.sha256
            and row["analysis_code_sha256"] == code_sha
            and row["timestamp"] <= experiment["start_time"]
            for row in freezes
        )
        if not matching:
            raise InvalidConfigError("final analysis requires matching pre-run freeze, rule, and analysis code hashes")
        if stored is not None:
            if stored["rule_sha256"] != rule.sha256 or stored["analysis_code_sha256"] != code_sha:
                raise AnalysisMismatchError("stored final analysis rule or code hash mismatch")
            bootstrap_samples = stored["bootstrap_samples"]
            analysis_seed = stored["analysis_seed"]
    report = _compute_report(experiment, planned, attempts, rule, bootstrap_samples, analysis_seed, code_sha)
    serialized = json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if stored is not None and phase == "final":
        if serialized != stored["report"]:
            raise AnalysisMismatchError("stored final analysis result mismatch")
        return report
    insert_analysis(db_path, {
        "analysis_id": str(uuid.uuid4()), "experiment_id": experiment_id, "phase": phase,
        "rule_sha256": rule.sha256, "rule_version": rule.rule_version,
        "analysis_code_sha256": code_sha, "bootstrap_samples": bootstrap_samples,
        "analysis_seed": analysis_seed, "n_tasks": report["n_tasks"],
        "estimate_pp": report["estimate_pp"], "ci_lo_pp": report["ci_lo_pp"],
        "ci_hi_pp": report["ci_hi_pp"], "verdict": report["verdict"],
        "reasons": json.dumps(report["reasons"]), "report": serialized,
        "timestamp": datetime.now(UTC).isoformat(), "forge_version": __version__,
    })
    return report


def _display(value: object, suffix: str = "") -> str:
    if value is None:
        return "undefined"
    return f"{value:.2f}{suffix}" if isinstance(value, float) else f"{value}{suffix}"


def render_report(report: dict[str, object], markdown: bool = False) -> str:
    lines = []
    if report["phase_warning"]:
        lines.append(f"**{PILOT_WARNING}**" if markdown else PILOT_WARNING)
    lines.append(f"Experiment {report['experiment_id']} ({report['phase']}); tasks={report['n_tasks']}; dropped={', '.join(report['dropped_tasks']) or 'none'}")
    lines.append("| Task | Baseline | Skill | Delta (pp) | Valid baseline | Valid skill |" if markdown else "task_id baseline skill delta_pp valid_baseline valid_skill")
    if markdown:
        lines.append("| --- | ---: | ---: | ---: | ---: | ---: |")
    for task in report["tasks"]:
        fields = (
            task["task_id"], _display(task["baseline_rate"] * 100, "%"),
            _display(task["skill_rate"] * 100, "%"), _display(task["delta_pp"]),
            str(task["baseline_valid"]), str(task["skill_valid"]),
        )
        lines.append("| " + " | ".join(fields) + " |" if markdown else " ".join(fields))
    lines.append(f"Mean task effect: {_display(report['estimate_pp'], ' pp')} (95% task-bootstrap CI {_display(report['ci_lo_pp'])} to {_display(report['ci_hi_pp'])} pp)")
    for condition in ("baseline", "skill"):
        data = report["telemetry"][condition]
        lines.append(
            f"{condition} telemetry: median tokens={_display(data['median_tokens'])} (missing {data['missing_tokens']}), "
            f"wall={_display(data['median_wall_seconds'])}s (missing {data['missing_wall_seconds']}), "
            f"commands={_display(data['median_command_count'])} (missing {data['missing_command_count']})"
        )
    telemetry = report["telemetry"]
    lines.append(
        f"Token change: {_display(telemetry['relative_token_change_pct'], '%')} "
        f"(95% task-bootstrap CI {_display(telemetry['relative_token_ci_lo_pct'])} to "
        f"{_display(telemetry['relative_token_ci_hi_pct'])}%; "
        f"reason={telemetry['relative_token_undefined_reason'] or 'defined'})"
    )
    for condition in ("baseline", "skill"):
        health = report["health"][condition]
        lines.append(
            f"{condition} health: crash/timeout/grader_error={_display(health['crash_rate_pct'], '%')}, "
            f"final infra_error={_display(health['final_infra_rate_pct'], '%')} "
            f"({health['final_infra_errors']}); statuses={json.dumps(health['status_counts'], sort_keys=True)}"
        )
    lines.append(f"Health: {'ok' if report['health']['ok'] else 'failed'}; guardrails: {'ok' if report['guardrails']['ok'] else 'failed'}; enough data: {report['enough_data']}")
    lines.append(f"Pending planned runs: {report['pending_runs']}; unlinked attempts: {json.dumps(report['unlinked_runs'], sort_keys=True)}")
    lines.append(f"Rule: {report['rule_version']} sha256={report['rule_sha256']}; analysis code sha256={report['analysis_code_sha256']}")
    lines.append(f"Verdict: {report['verdict']}")
    lines.append("Reasons: " + "; ".join(report["reasons"]))
    lines.append(report["regression_rate_limitation"])
    return "\n".join(lines) + "\n"
