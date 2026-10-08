# Systematic Debugging Final Evaluation

This package contains 15 held-out evidence tasks: three each in input
validation, state mutation, algorithm logic, integration/API boundaries, and
error/edge handling. The tasks were constructed after Systematic Debugging v2
was closed to tuning and must not be used to revise it.

The evaluated skill is `skills/systematic-debugging/v2/SKILL.md`, SHA-256
`a08970b2b2b04a09924097f31537899d1631d289d333408f889407b03a58676e`.
The final design pins `gpt-5.6-sol`, medium reasoning, baseline and skill, five
trials per condition, seed 20261008, and 150 observations. The unchanged v1
promotion rule retains the 25% token-increase guardrail.

The 45,000,000-token experiment ceiling is only a safety stop. The development
pilot averaged 135,907.6 tokens/run, projecting 20,386,140 tokens for 150 runs;
the ceiling is about 2.2 times that projection and is not an efficacy target.

Three separate smoke-only fixtures produce six infrastructure observations.
They are not present in the final manifest and cannot enter final evidence.

`FREEZE_INPUTS.json` records every pinned commit and reproducibility hash. Its
grader hash is SHA-256 over canonical JSON containing each final task ID,
grader command, protected paths, and sorted protected-test file paths and
content hashes. Forge's benchmark hash independently binds task definitions,
base/reference trees, and grader commands.

Deterministic preparation sequence:

```sh
PYTHONPATH=src python3 benchmarks/final/prepare.py --model gpt-5.6-sol
PYTHONPATH=src python3 benchmarks/final/validate.py
PYTHONPATH=src python3 -m forge.cli run-experiment benchmarks/final/generated/smoke.toml --plan-only
PYTHONPATH=src python3 -m forge.cli run-experiment benchmarks/final/generated/manifest.toml --plan-only
```

After audit approval, freeze the final experiment before any live final run:

```sh
PYTHONPATH=src python3 -m forge.cli freeze benchmarks/final/generated/manifest.toml --db benchmarks/final/generated/final.sqlite --rule benchmarks/final/final-rule.toml
```

Do not run or analyze final observations before the matching freeze exists. Do
not tune v2 after inspecting smoke or final outcomes.
