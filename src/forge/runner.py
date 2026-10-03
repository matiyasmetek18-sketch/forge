from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import tempfile
import uuid

from forge import __version__
from forge.checkout import CheckoutError, disposable_clone
from forge.db import RunRecord, insert_run
from forge.integrity import restore_protected_paths, uses_pytest
from forge.process import ProcessResult, allowed_environment, run_command
from forge.task import InvalidConfigError, TaskDefinition, load_task


VALID_CONDITIONS = {"baseline", "skill"}


@dataclass(frozen=True)
class RunOnceRequest:
    task_path: Path
    condition: str
    trial: int
    seed: int
    experiment_id: str
    db_path: Path
    agent_cmd: list[str]


@dataclass(frozen=True)
class RunOnceResult:
    run_id: str
    status: str


def run_once(request: RunOnceRequest) -> RunOnceResult:
    if request.condition not in VALID_CONDITIONS:
        raise InvalidConfigError(f"condition must be one of: {', '.join(sorted(VALID_CONDITIONS))}")
    if not request.agent_cmd:
        raise InvalidConfigError("agent_cmd must not be empty")

    run_id = str(uuid.uuid4())
    start_time = _now()
    logs = Path(tempfile.mkdtemp(prefix=f"forge-run-{run_id}-logs-"))
    stdout_path = logs / "agent.stdout"
    stderr_path = logs / "agent.stderr"

    task: TaskDefinition | None = None
    status = "infra_error"
    agent_result: ProcessResult | None = None
    grader_result: ProcessResult | None = None
    changed_paths: list[str] = []

    try:
        task = load_task(request.task_path)
        with disposable_clone(task.repo_path, task.base_commit) as worktree:
            agent_env = allowed_environment(logs / "agent-home", {"FORGE_AGENT_PROMPT": task.agent_prompt})
            agent_result = run_command(
                request.agent_cmd,
                worktree,
                task.agent_timeout_s,
                stdout_path,
                stderr_path,
                agent_env,
            )
            changed_paths = restore_protected_paths(worktree, task.base_commit, task.grader_paths, uses_pytest(task.grader_cmd))
            grader_env = allowed_environment(logs / "grader-home")
            grader_result = run_command(
                task.grader_cmd,
                worktree,
                task.grader_timeout_s,
                logs / "grader.stdout",
                logs / "grader.stderr",
                grader_env,
            )
            status = _classify(agent_result, grader_result)
    except InvalidConfigError:
        status = "invalid_config"
    except CheckoutError:
        status = "infra_error"
    except Exception:
        status = "infra_error"

    record = _record(
        run_id=run_id,
        request=request,
        task=task,
        status=status,
        agent_result=agent_result,
        grader_result=grader_result,
        changed_paths=changed_paths,
        start_time=start_time,
        end_time=_now(),
        stdout_path=stdout_path,
        stderr_path=stderr_path,
    )
    insert_run(request.db_path, record)
    return RunOnceResult(run_id, status)


def _classify(agent: ProcessResult, grader: ProcessResult) -> str:
    if grader.timed_out or (grader.exit_code not in (0, 1)):
        return "grader_error"
    if agent.timed_out:
        return "agent_timeout"
    if agent.exit_code != 0:
        return "agent_error"
    if grader.exit_code == 0:
        return "passed"
    return "failed"


def _record(
    run_id: str,
    request: RunOnceRequest,
    task: TaskDefinition | None,
    status: str,
    agent_result: ProcessResult | None,
    grader_result: ProcessResult | None,
    changed_paths: list[str],
    start_time: str,
    end_time: str,
    stdout_path: Path,
    stderr_path: Path,
) -> RunRecord:
    return RunRecord(
        run_id=run_id,
        experiment_id=request.experiment_id,
        task_id=task.task_id if task else "unknown",
        task_version=task.version if task else "unknown",
        condition=request.condition,
        trial=request.trial,
        seed=request.seed,
        base_commit=task.base_commit if task else "unknown",
        status=status,
        agent_exit_code=agent_result.exit_code if agent_result else None,
        grader_exit_code=grader_result.exit_code if grader_result else None,
        protected_paths_modified=json.dumps(changed_paths),
        start_time=start_time,
        end_time=end_time,
        agent_cmd=json.dumps(request.agent_cmd),
        stdout_path=str(stdout_path),
        stderr_path=str(stderr_path),
        forge_version=__version__,
    )


def _now() -> str:
    return datetime.now(UTC).isoformat()
