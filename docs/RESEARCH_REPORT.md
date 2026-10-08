# Forge V1 Research Report

## Abstract

Forge evaluates whether a fixed procedural skill changes a coding agent's
debugging performance under controlled conditions. Development work produced
Systematic Debugging v2; a separately constructed, frozen held-out experiment
then compared it with a no-skill baseline. Across 15 tasks and 150 observations,
both conditions passed every run. The estimated success effect was 0.00
percentage points with a task-clustered 95% bootstrap interval of 0.00 to 0.00.
The frozen promotion rule returned **REJECT: effect_below_threshold**. This is a
decision about this candidate under this benchmark and rule, not evidence that
procedural skills are universally ineffective. Complete baseline success
created a ceiling that prevented detection of a positive binary effect.

## Question And Hypotheses

Research question: does reusable systematic-debugging procedure improve a
coding agent's task success relative to the same agent receiving only the task
prompt, while remaining within precommitted reliability and cost guardrails?

- Primary hypothesis: the skill has a positive mean task-level success effect
  whose lower 95% confidence bound exceeds 3 percentage points.
- Guardrail hypotheses: the skill increases median tokens by at most 25%, does
  not reduce any analyzed task by more than 40 points, and preserves experiment
  health.
- Null operational outcome: evidence is insufficient for promotion or places
  the effect below the frozen threshold.

## System

Forge reads task TOML files containing a canonical Git repository, pinned base
and reference commits, an agent prompt, protected grader paths, commands, and
timeouts. An experiment manifest fixes tasks, conditions, trial count, seed,
agent configuration, and cumulative safety limits. A seeded scheduler persists
the full plan before execution and resumes without replacing completed slots.

For each run Forge exports the base tree into a temporary Git repository with
exactly one commit and no remote. The agent can use ordinary Git commands but
cannot inspect later canonical history through its local object database. The
runner uses an allowlisted environment, a process group, and bounded execution.
For Codex it creates a private temporary `CODEX_HOME` containing only a copied
authentication file and invokes `codex exec --json --sandbox workspace-write`.

After agent exit, Forge records tampering and restores protected inputs from
the snapshot. Pytest configuration and `conftest.py` files are protected for
pytest graders; test modules, startup hooks, and stdlib-shadowing files are
protected for unittest graders. Grading is condition-blind. Results, hashes,
process outcomes, prompts, and telemetry are stored in SQLite.

## Intervention

Baseline runs received `task.agent_prompt` byte-for-byte. Skill runs received a
fixed version-1 injection template containing the immutable skill text followed
by the same prompt. The skill was never copied into the run repository. Model,
reasoning effort, snapshot, environment, sandbox, limits, and grader were
identical across conditions.

Systematic Debugging v1 specified: reproduce, localize, hypothesize,
discriminate, make the smallest justified fix, verify narrowly, verify broadly,
and review the diff. V2 retained these safeguards but made them adaptive:
additional investigation or verification was warranted only when it could
change the diagnosis or confidence.

## Development Evidence

The 10-task pilot is development data, not held-out evidence. V1 produced 24/30
baseline passes and 27/30 skill passes. The mean task-level difference was
+10.00 points (task-clustered 95% CI 0.00 to +23.33). Differences appeared on
`event_dispatch` (+66.67 points) and `parse_limit` (+33.33); the other eight
tasks showed no measured success difference. Median tokens rose from 107,183
to 158,591.5 (+47.96%; 95% CI +23.75% to +69.12), violating the 25% guardrail.
The pilot verdict was INCONCLUSIVE.

Trajectory review suggested that structured localization and discriminating
checks helped on the two differentiated tasks, while mechanical exploration,
repeated verification, and procedural narration added cost on ceiling tasks.
This observation informed v2. Therefore all 10 pilot tasks are contaminated for
v2 evaluation and cannot be relabeled as final evidence. The final benchmark
was newly constructed after v2 was fixed.

The pilot-to-v2 comparison was not randomized and v1 was not evaluated on the
held-out final set. Consequently, v2's lower final token median cannot establish
that the revision caused an efficiency improvement relative to v1.

## Held-Out Design And Freeze

The final package contains 15 tasks, three in each of five families: input
validation, state mutation, algorithm logic, integration/API boundaries, and
error/edge handling. No final task reused a pilot repository, statement,
solution, or bug mechanism. Three additional smoke tasks tested infrastructure
and were excluded from evidence.

The final experiment fixed:

| Item | Value |
| --- | --- |
| Experiment | `systematic-debugging-final-v1` |
| Agent | Codex CLI 0.157.1 |
| Model / effort | `gpt-5.6-sol` / `medium` |
| Conditions | baseline, Systematic Debugging v2 |
| Tasks / trials | 15 / 5 per condition |
| Planned observations | 150 |
| Scheduler seed | 20261008 |
| Bootstrap samples / seed | 10,000 / 12345 |

Before any evidence run, Forge froze hashes for the manifest, benchmark, skill,
promotion rule, and analysis source. The first final analysis was then stored
immutably and subsequent analysis must reproduce its serialized result. The
dedicated six-run smoke was non-evidence and did not alter the frozen plan.

## Statistical Method

For each task, Forge computes the baseline and skill pass proportions from
valid final attempts, then averages their difference equally across tasks. A
nonparametric task-clustered bootstrap resamples tasks, preserving within-task
trials and condition pairing, to form a 95% interval. The same task-cluster
resampling estimates the relative change in condition-level median tokens.

The frozen rule requires more than a 3-point lower confidence bound for
promotion, no more than 25% median-token increase, no task drop worse than 40
points, crash rates below 5% per condition, balanced final infrastructure
errors, at least 10 tasks, and at least 3 valid trials per condition. Agent,
timeout, and grader failures are unsuccessful outcomes; final infrastructure
errors are excluded and reported separately.

## Final Results

| Measure | Baseline | Skill | Comparison |
| --- | ---: | ---: | ---: |
| Passed | 75/75 | 75/75 | 0.00 pp |
| Median tokens | 111,415 | 106,863 | -4.09% |
| Median runtime | 38.51 s | 35.37 s | descriptive |
| Median commands | 6 | 5 | descriptive |

The task-level success CI was 0.00 to 0.00 points. The token-change CI was
-14.46% to +3.17%. All telemetry was present; all 150 planned observations
completed; no agent, grader, or infrastructure errors occurred; health and
guardrails passed. The immutable verdict was **REJECT**, reason
`effect_below_threshold`.

## Interpretation

The experiment provides no evidence that v2 improves binary success on these
tasks. It also cannot estimate how much help the procedure might provide below
the observed ceiling: every baseline run succeeded. The lower token, runtime,
and command medians are compatible with reduced overhead, but token uncertainty
crosses zero and these secondary observations do not prove a causal v1-to-v2
efficiency gain.

REJECT applies only to the frozen promotion criterion for Systematic Debugging
v2 on this evaluation. It is not a universal rejection of debugging procedures,
prompted skills, or effects on harder tasks, different agents, or richer outcome
measures.

## Threats And Limitations

- Ceiling saturation eliminates power to detect a positive binary success
  effect and suggests the held-out tasks were too easy for this model.
- Fifteen compact synthetic Python tasks have limited ecological validity for
  large, multilingual, dependency-heavy repositories.
- Graders establish specified behavior, not maintainability, explanation
  quality, or latent regressions outside their assertions.
- V1 does not measure regression of tests that already passed and has no
  regression-rate guardrail.
- One model, reasoning setting, CLI version, and local host configuration limit
  generalization.
- Task-cluster bootstrap uncertainty reflects the sampled task set but not
  model or environment families absent from the design.
- Snapshot isolation is not a security boundary against an agent that knows
  canonical host paths; new-session children may escape process-group cleanup.
- Development inspection influenced v2, making the pilot permanently
  ineligible as held-out evidence for that version.

## Conclusion And Future Work

Forge V1 successfully executed a healthy, reproducible, frozen comparison and
correctly declined promotion when its primary outcome saturated. The sound
conclusion is narrow: Systematic Debugging v2 did not clear the precommitted
success criterion on this held-out benchmark.

Future research should freeze a new skill version, if any, before constructing
new held-out tasks; target calibrated baseline difficulty; include larger and
more realistic repositories; precommit richer outcomes such as partial credit,
regressions, and patch quality; and replicate across models and reasoning
settings. The completed final set must remain immutable and must not be reused
as fresh confirmatory evidence after inspection.
