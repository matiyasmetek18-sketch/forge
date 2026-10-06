# Forge

Forge is an evidence-driven evaluation runner for coding-agent procedural skills.
Each run exports the tree at `base_commit` into a disposable Git repository
with one new commit and no remote or earlier history. Forge restores protected
grader files from that snapshot commit, grades the result, records it in SQLite,
and cleans up.

## Test

```sh
pytest
```

## Run Once

```sh
forge run-once TASK.toml \
  --condition baseline \
  --trial 1 \
  --seed 123 \
  --experiment-id EXPERIMENT \
  --db forge.sqlite \
  --agent-cmd python stub_agent.py
```

For a skill run, use `--condition skill --skill /path/to/SKILL.md`.
`--skill-id NAME` optionally overrides the ID; otherwise `SKILL.md` uses its
parent directory name and other skill files use their file stem.
`--skill` is invalid for baseline runs. Baseline passes the task prompt unchanged
in `FORGE_AGENT_PROMPT`; skill runs prepend the versioned skill template and
skill text. Forge does not copy the skill file into the run repository.
SQLite records the final prompt and its SHA-256, the skill file's SHA-256 and
ID, template version, and snapshot tree SHA. Existing version 1 databases
migrate in place; older rows keep NULL in the new columns.

To evaluate with Codex instead of `--agent-cmd`, use `--agent codex --model MODEL
--reasoning-effort EFFORT`. `--codex-bin` defaults to `codex`; `--codex-auth`
defaults to `auth.json` in the user's `CODEX_HOME` or `~/.codex`. Forge passes
the final prompt on stdin, runs Codex with `workspace-write`, and records JSONL
usage, tool counts, elapsed time, the requested model and effort, and the
`codex --version` result. Version 1 and 2 databases migrate in place.

Codex receives a temporary home containing only a private copy of `auth.json`;
Forge deletes it after the run. This excludes personal Codex settings from the
experimental conditions, but **does not protect the real home**: sandboxed
commands can read the real auth file. Forge detects exact auth string values of
at least 20 characters in logs and checkout files, redacts matches in stored
logs, and records `secret_exposure=1`. Encoded, split, or transformed secrets
are not detected. Logs default to a temporary directory outside the repo and
must never be committed or shared.

Codex may refresh or rotate the copied credential during a run. If that
invalidates the user's real login, they may need to run `codex login` again;
Forge does not reconcile credentials.

## Experiments

Validate each task with `forge validate-task TASK.toml --db runs.sqlite` before
running an experiment. A task may set `reference_commit`; validation grades
fresh base and reference snapshots and records the checks in SQLite.

`forge run-experiment MANIFEST.toml` uses a seeded, persisted plan. Use
`--plan-only` to inspect it or `--limit N` to execute at most N attempts now;
repeat the command to resume. `db`, `tasks`, `skill`, and `codex_auth` paths
are relative to the manifest; `argv` is passed directly to the run checkout.
Runs with `infra_error` are retried at most once. Every other outcome,
including `agent_error` and `agent_timeout`, stands and counts as unsuccessful.
The token budget checks usage already recorded before each run, so one run can
cross the cap; runs without telemetry still count against `max_total_runs`.
Forge stops if manifest, task, skill, or Codex version inputs drift between
planned runs.

A manifest uses flat TOML keys: `experiment_id`, `phase` (`pilot` or `final`),
`db`, `tasks`, `conditions`, `trials_per_condition`, `seed`, `agent`,
`max_total_runs`, and `max_total_tokens`. Add `skill` and optional `skill_id`
when using the skill condition. For `agent = "cmd"`, set `argv`; for
`agent = "codex"`, set `model` and `reasoning_effort`, with optional
`codex_bin` and `codex_auth`.

Before a final-phase run, record the manifest, benchmark, and skill hashes with
`forge freeze MANIFEST.toml --db runs.sqlite` (the same DB named in the
manifest). Final runs require an exact matching freeze; pilot runs do not.

For pytest graders, Forge also restores pytest configuration, conftest files,
and test modules. For unittest graders, it restores test modules, Python startup
hooks, and modules that shadow the standard library. The grader command must
exit 0 for solved, 1 for not solved, and any other code is `grader_error`;
this follows pytest exit-code conventions.

Isolation limits: an agent that knows the canonical repository path can still
access it directly. A child that creates a new process session can escape
process-group cleanup.
