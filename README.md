# Forge

Forge is an evidence-driven evaluation runner for coding-agent procedural skills.
This first slice runs one task in an isolated git worktree, restores protected
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
