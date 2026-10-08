# Forge V1 Reproducibility Audit

Audit date: 2026-10-08. Result: **PASS with no frozen-evidence mismatch**.

The audit was read-only against the completed experiment database. It
recomputed source-controlled hashes where possible, resolved all pinned Git
objects, compared database metadata with the freeze package, and reconciled the
stored run plan and outcomes. It did not rerun an agent, mutate an observation,
or regenerate the benchmark.

## Frozen Inputs

| Artifact | Recorded SHA-256 | Audit |
| --- | --- | --- |
| Final manifest | `45afbb93e20415086b3b0019da6ffe66224986f087939c4b6d1d9e956ff3fbe2` | match |
| Benchmark | `66e96af2fdc51f44d6250d3c8ce8d7cd260da14913f88c9b019bfdeaffacc825` | match |
| Protected graders | `26fe489737f1581595162e0221a2fd7c567282ae1aded4501d18e3706259ee91` | match package/materialized protected files |
| Systematic Debugging v2 | `a08970b2b2b04a09924097f31537899d1631d289d333408f889407b03a58676e` | match |
| Promotion rule | `26828d797d81dc686b2a441c8afb61d66e3579f7d3631061bef0076e448a5734` | match |
| Analysis source | `268fcd20a41992d76d53327f8aeaed6559109771544e8ec2bf7e50fc75a4f25a` | match |

For historical context, v1 remains
`95437cbf0e659d93999fd58863210099ef7fc122b6803005d23757fc4e37ec6d`.
The complete task commit inventory is preserved in
`benchmarks/final/FREEZE_INPUTS.json`; every one of the 15 base and reference
commits resolved and matched its generated task definition.

## Configuration And Plan

| Field | Verified value |
| --- | --- |
| Experiment | `systematic-debugging-final-v1` |
| Phase | `final` |
| Model | `gpt-5.6-sol` |
| Reasoning | `medium` |
| Agent version | `codex-cli 0.157.1` |
| Conditions | baseline, skill |
| Tasks | 15 |
| Trials per condition/task | 5 |
| Planned observations | 150 |
| Scheduler seed | 20261008 |
| Bootstrap samples | 10,000 |
| Analysis seed | 12345 |

The evidence was executed by Forge 0.1.0; the documentation-complete release
package is versioned 1.0.0. No runner or analysis behavior changed between the
recorded evidence and this release pass.

The persisted plan contains 150 unique task/condition/trial slots, 75 per
condition, with zero pending slots. All task repositories contain the pinned
base and reference commits. The final manifest's benchmark hash independently
binds the task definition, commits/trees, prompts, and grader command.

## Outcomes And Freeze

The database contains one final experiment, one pre-run freeze, one immutable
final analysis, and 150 linked final runs. Baseline has 75 `passed`; skill has
75 `passed`; all telemetry is present. The stored analysis records 0.00 points
with CI 0.00 to 0.00, health and guardrails OK, and `REJECT` with
`effect_below_threshold`.

The freeze row matches the manifest, benchmark, skill, rule, and analysis
hashes above. Recomputing the final report from the stored plan is byte-equal to
the immutable analysis record, as enforced by Forge's final-analysis path.
The audited local completed database has SHA-256
`b773469dc1855b310981ac27d2585b3a086edc2614fcef75a7ea05dd54e31c44`.

## Experiment History

Existing development and evidence databases remain separate and unchanged:

| Experiment | Runs | Recorded statuses |
| --- | ---: | --- |
| `systematic-debugging-smoke-v1` | 6 | 6 `agent_error` |
| `systematic-debugging-smoke-v2` | 6 | 4 passed, 2 failed |
| `systematic-debugging-pilot-v2` | 60 | 51 passed, 9 failed |
| `systematic-debugging-final-smoke-v1` | 6 | 6 passed |
| `systematic-debugging-final-v1` | 150 | 150 passed |

Generated repositories and SQLite databases are intentionally ignored by Git
because they contain run logs and local absolute paths. `FREEZE_INPUTS.json`,
the source fixtures, preparation code, rule, skill, and deterministic tests are
the source-controlled reproducibility package. Preserving the completed SQLite
database as a release asset is required to reproduce the exact recorded
analysis; publishing that asset requires a deliberate secret review.

## Residual Reproducibility Limits

- Rebuilding fixture repositories is deterministic under the preparation
  script's fixed Git identity and dates, but Git and platform versions remain
  part of the execution environment.
- Exact model behavior depends on a remotely served model identified by name;
  the model weights are not archived by Forge.
- Local ignored databases are not protected by Git. Their backups and release
  checksums must be managed outside the repository.
- The recorded grader hash is a package-level assertion over protected test
  content; the materialized grader files were also checked against their pinned
  repositories and deterministic benchmark tests.
- Security isolation has the host-path and process-session limits documented in
  the root README.
