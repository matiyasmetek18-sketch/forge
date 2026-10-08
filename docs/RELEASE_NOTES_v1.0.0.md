# Forge v1.0.0

Forge V1 is an evidence-driven runner for controlled baseline-versus-skill
evaluation of coding agents. This release includes history-free task snapshots,
protected condition-blind grading, resumable seeded plans, Codex telemetry,
frozen final analysis, the Systematic Debugging skill versions, and the complete
source package for the held-out benchmark.

## Frozen Evaluation

- Experiment: `systematic-debugging-final-v1`
- 15 held-out tasks, 5 trials per condition, 150 observations
- Model: `gpt-5.6-sol`, reasoning effort `medium`
- Baseline: 75/75 passed
- Systematic Debugging v2: 75/75 passed
- Mean task-level success effect: 0.00 percentage points
- Task-clustered 95% CI: 0.00 to 0.00 percentage points
- Health: OK; guardrails: OK; all planned runs complete
- Frozen verdict: **REJECT** (`effect_below_threshold`)

Every baseline observation passed, saturating the binary outcome. The benchmark
therefore could not detect a positive success-rate effect. The verdict rejects
promotion under the precommitted rule; it does not establish that procedural
skills are universally ineffective.

Skill runs had lower descriptive medians for tokens (106,863 vs. 111,415),
runtime (35.37 s vs. 38.51 s), and commands (5 vs. 6). The token change was
-4.09% with a 95% task-clustered interval of -14.46% to +3.17%; it does not
prove that the pilot-informed v2 revision caused an efficiency improvement over
v1.

## Reproducibility And Data

The final manifest, benchmark, skill, rule, and analysis hashes are recorded in
`benchmarks/final/FREEZE_INPUTS.json`. The research report and reproducibility
audit are under `docs/`.

The original `final.sqlite` is intentionally not included: the publication
audit found no credential exposure, but the file contains local paths, prompts,
and machine/run metadata. Aggregate evidence and checksums are included without
publishing that unsanitized artifact.

Licensed under Apache License 2.0.
