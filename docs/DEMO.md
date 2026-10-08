# Forge V1 CLI Demonstration

This walkthrough uses the completed final database as **existing recorded
evidence**. It does not launch an agent, create replacement observations, or
modify the frozen database. Run it from the repository root on a machine where
the ignored `benchmarks/final/generated/final.sqlite` artifact is available.

## 1. Protect The Evidence

Work on a copy:

```sh
cp benchmarks/final/generated/final.sqlite /tmp/forge-v1-demo.sqlite
```

Confirm the experiment and freeze metadata:

```sh
sqlite3 -readonly /tmp/forge-v1-demo.sqlite \
  "SELECT experiment_id, phase, model, reasoning_effort, agent_version
   FROM experiments;
   SELECT manifest_sha256, benchmark_hash, skill_sha256, rule_sha256,
          analysis_code_sha256
   FROM freezes;"
```

The freeze binds the treatment, benchmark, decision rule, and analysis code
before evidence collection.

## 2. Inspect Isolation And Conditions

Each observation records the exported tree hash. This query shows that every
task used the same snapshot in baseline and skill:

```sh
sqlite3 -readonly /tmp/forge-v1-demo.sqlite \
  "SELECT task_id, count(DISTINCT snapshot_tree_sha) AS snapshots
   FROM runs GROUP BY task_id ORDER BY task_id;"
```

Every row should report one snapshot. Baseline rows have NULL skill identity;
skill rows bind the frozen skill hash and prompt-template version:

```sh
sqlite3 -readonly /tmp/forge-v1-demo.sqlite \
  "SELECT condition, count(*) AS runs,
          count(skill_sha256) AS skill_bound,
          min(prompt_template_version), max(prompt_template_version)
   FROM runs GROUP BY condition ORDER BY condition;"
```

The same task grader is applied only after Forge restores protected files from
the snapshot. Tampering evidence is retained in `changed_paths`; it does not
change the grader command or condition label.

## 3. Inspect Outcomes And Telemetry

```sh
sqlite3 -readonly /tmp/forge-v1-demo.sqlite \
  "SELECT condition, status, count(*)
   FROM runs GROUP BY condition, status ORDER BY condition, status;
   SELECT condition,
          round(avg(input_tokens + output_tokens), 1) AS mean_tokens,
          round(avg(wall_seconds), 2) AS mean_seconds,
          round(avg(command_count), 2) AS mean_commands
   FROM runs GROUP BY condition ORDER BY condition;"
```

The expected status result is 75 passed runs per condition with complete token,
latency, and tool telemetry.

## 4. Verify Frozen Analysis

Run the analyzer against the disposable copy with the frozen rule:

```sh
PYTHONPATH=src python3 -m forge.cli analyze \
  --db /tmp/forge-v1-demo.sqlite \
  --experiment-id systematic-debugging-final-v1 \
  --rule benchmarks/final/final-rule.toml
```

For a final-phase database, Forge requires the pre-run freeze, uses the stored
bootstrap settings, recomputes the report, and rejects any mismatch with the
immutable first analysis. The expected decision is `REJECT` with reason
`effect_below_threshold`; health and guardrails remain OK.

This demo deliberately has no `run-experiment` command. It demonstrates the
evaluation pipeline without spending model requests or altering evidence.
