# Systematic Debugging Pilot

**Development data, not final evidence.** These ten fixtures may be used to debug
Forge, estimate cost and variance, check floor/ceiling effects, and refine task
construction. They must never be relabeled as a held-out final set. A separate
set must be constructed and frozen before any final evaluation.

Research question: does reusable systematic-debugging procedure improve a coding
agent's success on debugging tasks, compared with the same agent and prompt
without that skill? The pilot candidate was
`skills/systematic-debugging/v1/SKILL.md` (SHA-256
`95437cbf0e659d93999fd58863210099ef7fc122b6803005d23757fc4e37ec6d`).
It teaches reproduce, localize, hypothesize, discriminate, fix, verify locally,
verify globally, and review. It contains no task-specific answers.

## Pilot-informed v2

Systematic Debugging v2 was revised after inspecting outcomes and trajectories
from this pilot. It makes the same procedure adaptive to reduce unnecessary
exploration and verification. Its candidate is
`skills/systematic-debugging/v2/SKILL.md` (SHA-256
`a08970b2b2b04a09924097f31537899d1631d289d333408f889407b03a58676e`).

Because these ten tasks informed v2, neither their pilot results nor reruns can
serve as held-out final evidence for v2. Freeze the exact v2 skill before final
evaluation and evaluate it only on newly constructed held-out tasks that were
not inspected or used during this revision.

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
forge run-experiment benchmarks/pilot/generated/smoke.toml --plan-only
forge run-experiment benchmarks/pilot/generated/manifest.toml --plan-only
```

These commands materialize fixtures, run graders, and display both plans; none
launch an agent. Plan commands may query `codex --version`. The completed v2
manifest pinned `gpt-5.6-sol`, `reasoning_effort = "medium"`, seed 20261006,
3 trials per condition, both conditions, `max_total_runs = 66`, and a
15,000,000-token ceiling. Ten valid tasks produced 60 planned runs (30 per
condition); the extra six-run allowance was only for infrastructure retries.
The token ceiling checks usage before each run and one run can cross it.

The [audit](AUDIT.md) selects `parse_tags`, `event_dispatch`, and
`weighted_route` for a separate six-slot smoke: one baseline and one skill run
per task, seed 20261007, `max_total_runs = 8`, and a 1,250,000-token ceiling.
Preparation uses the **same explicitly supplied model**, reasoning effort, and
skill for both manifests. Validation records the three selected tasks in the
separate smoke DB. No smoke result enters the full pilot DB.

**Do not execute during preparation.** After human approval, run the smoke with:

```sh
forge run-experiment benchmarks/pilot/generated/smoke.toml
```

Afterward, analyze that smoke with
`forge analyze --db benchmarks/pilot/generated/smoke-v2.sqlite --experiment-id systematic-debugging-smoke-v2 --rule benchmarks/pilot/pilot-rule.toml`.
Its sample is too small for efficacy claims. The full pilot, only after smoke
review and authorization, uses
`forge run-experiment benchmarks/pilot/generated/manifest.toml`.
Pilot analysis, after actual full-pilot runs, may use
`forge analyze --db benchmarks/pilot/generated/pilot-v2.sqlite --experiment-id systematic-debugging-pilot-v2 --rule benchmarks/pilot/pilot-rule.toml`.
Its output remains development information, not final evidence.

Limits: these compact synthetic Python tasks may not represent real projects;
the grader only checks specified behavior. The existing sandbox does not block
an agent that knows the Forge checkout path from reading source fixtures there,
including references, although the run checkout itself does not contain them.
Use a stronger read boundary before treating adversarial agent behavior as
evidence. Model availability and actual token cost remain unverified.
