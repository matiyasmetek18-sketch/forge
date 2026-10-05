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
`--skill` is invalid for baseline runs. Baseline passes the task prompt unchanged
in `FORGE_AGENT_PROMPT`; skill runs prepend the versioned skill template and
skill text. Forge does not copy the skill file into the run repository.
SQLite records the final prompt and its SHA-256, the skill file's SHA-256 and
stem, template version, and snapshot tree SHA. Existing version 1 databases
migrate in place; older rows keep NULL in the new columns.

For pytest graders, Forge also restores pytest configuration, conftest files,
and test modules. For unittest graders, it restores test modules, Python startup
hooks, and modules that shadow the standard library. The grader command must
exit 0 for solved, 1 for not solved, and any other code is `grader_error`;
this follows pytest exit-code conventions.

Isolation limits: an agent that knows the canonical repository path can still
access it directly. A child that creates a new process session can escape
process-group cleanup.
