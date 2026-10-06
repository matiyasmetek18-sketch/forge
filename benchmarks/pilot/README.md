# Systematic Debugging Pilot

**Development data, not final evidence.** These ten fixtures may be used to debug
Forge, estimate cost and variance, check floor/ceiling effects, and refine task
construction. They must never be relabeled as a held-out final set. A separate
set must be constructed and frozen before any final evaluation.

Research question: does reusable systematic-debugging procedure improve a coding
agent's success on debugging tasks, compared with the same agent and prompt
without that skill? The fixed candidate is
`skills/systematic-debugging/v1/SKILL.md` (SHA-256
`95437cbf0e659d93999fd58863210099ef7fc122b6803005d23757fc4e37ec6d`).
It teaches reproduce, localize, hypothesize, discriminate, fix, verify locally,
verify globally, and review. It contains no task-specific answers.

| Family | Tasks |
| --- | --- |
| Input / validation | `parse_limit`, `parse_tags` |
| State / mutation | `cart_snapshot`, `event_dispatch` |
| Algorithm / logic | `booking_overlap`, `weighted_route` |
| Integration / API boundary | `pagination_cursor`, `timestamp_offset` |
| Error handling / edge cases | `retry_scope`, `config_fallback` |

Each case has pilot metadata, a buggy `base/`, a fixed `reference/`, and unchanged
behavioral `tests/`. Preparation makes a local Git repo with separate pinned
base and reference commits and a Forge task TOML. The runner exports only the
buggy base tree into its single-commit agent checkout; reference history and
solutions are absent there. Forge restores protected `tests/` before grading.
Validation repeats the authoritative unittest grader three times on each state,
requiring base failure, reference success, unchanged protected files, and a
hidden reference in the agent snapshot.

From the Forge repository root, after `pip install -e .`, choose and verify a
Codex model ID for this environment. No model is guessed by the template:

```sh
python3 benchmarks/pilot/prepare.py --model YOUR_PINNED_MODEL
python3 benchmarks/pilot/validate.py
forge run-experiment benchmarks/pilot/generated/manifest.toml --plan-only
```

These commands materialize fixtures, run graders, and display the plan; none
launch an agent. The last command may query `codex --version`. The committed
template pins `reasoning_effort = "medium"`, seed 20261006, 3 trials per
condition, both conditions, `max_total_runs = 66`, and a 1,500,000-token
ceiling. Ten valid tasks produce 60 planned runs (30 per condition); the extra
six-run allowance is only for infrastructure retries. The token ceiling checks
usage before each run and one run can cross it. Cost in currency cannot be
estimated without verified model pricing and a smoke measurement.

**Do not execute during preparation.** After human approval, the intended small
smoke command is:

```sh
forge run-experiment benchmarks/pilot/generated/manifest.toml --limit 2
```

Pilot analysis, after actual runs, may use
`forge analyze --db benchmarks/pilot/generated/pilot.sqlite --experiment-id systematic-debugging-pilot-v1 --rule benchmarks/pilot/pilot-rule.toml`.
Its output remains development information, not final evidence.

Limits: these compact synthetic Python tasks may not represent real projects;
the grader only checks specified behavior. The existing sandbox does not block
an agent that knows the Forge checkout path from reading source fixtures there,
including references, although the run checkout itself does not contain them.
Use a stronger read boundary before treating adversarial agent behavior as
evidence. Model availability and actual token cost remain unverified.
