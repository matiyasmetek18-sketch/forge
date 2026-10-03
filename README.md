# Forge

Forge is an evidence-driven evaluation runner for coding-agent procedural skills.
This first slice runs one task in a disposable local clone, restores protected
grader files, grades the result, classifies the outcome, records it in SQLite,
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

The agent prompt is passed to the child process in `FORGE_AGENT_PROMPT`.
For pytest graders, Forge also restores pytest configuration, conftest files,
and test modules to the pinned commit before grading. The grader command must
exit 0 for solved, 1 for not solved, and any other code is `grader_error`;
this follows pytest exit-code conventions.
