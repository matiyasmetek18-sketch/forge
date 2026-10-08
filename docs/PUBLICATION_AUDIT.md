# Forge V1 Publication Audit

Audit date: 2026-10-08. Scope: tracked files, every Git blob reachable from
`--all`, ignored generated benchmark artifacts, and the original completed
`benchmarks/final/generated/final.sqlite`.

## Repository And History

- 161 tracked files and 256 unique historical text blobs were scanned for
  private-key headers, common cloud/API token formats, JWTs, credential-bearing
  URLs, personal home paths, and transcript markers.
- No credential, private key, token, personal home path, or transcript marker
  was detected in tracked or historical blob content.
- Git commit metadata contains the expected author identity. It includes 51
  commits using a university email address and one using a Gmail address. These
  are publication identifiers, not credentials; rewriting them would change all
  descendant commit IDs and the release tag.
- Generated directories and SQLite databases remain ignored and are not part of
  the release tree.

## Generated Artifacts

The scan covered 704 generated text files. No credential pattern, personal
email, or transcript marker was found. Thirty-two generated manifest/task TOML
files contain local absolute paths rooted in the developer's home directory.
They must not be published unchanged. These files are reproducible outputs and
remain excluded by `.gitignore`.

Generated fixture repositories use the non-routable identity
`fixture@forge.invalid`. Referenced run logs no longer exist at any of the 300
paths recorded by the final database, so no logs are candidates for release.

## Final Database

The original database passed `PRAGMA integrity_check`, has
`secret_exposure = 0` across all runs, and produced no matches for the audited
credential patterns. Its SHA-256 remained unchanged throughout the audit:

`b773469dc1855b310981ac27d2585b3a086edc2614fcef75a7ea05dd54e31c44`

It is nevertheless **not approved for publication as-is** because:

- `experiments.manifest_text` contains local absolute paths;
- `runs.stdout_path` and `runs.stderr_path` contain machine-local temporary
  paths, although their target files no longer exist;
- all 150 final prompts are stored in `runs.final_prompt`, including the skill
  text in 75 treatment rows;
- run UUIDs, seeds, timestamps, OS/Python metadata, and local execution details
  remain present.

The prompts duplicate source-controlled task and skill content and no detected
secret, but publishing them and the machine metadata should be a deliberate
data-release decision.

## Minimal Publication Options

The safest V1 release publishes source, reports, aggregate results, and hashes,
but not any SQLite database. If row-level data is later required, create a
separately named derivative copy; replace local manifest/log paths with portable
placeholders; remove redundant prompt payloads and unnecessary host metadata;
retain task, condition, trial, outcome, telemetry, hashes, plan position, and
freeze/analysis records; then rerun integrity and secret scans. Keep the
original database untouched and publish both its original checksum and the
derived artifact's new checksum plus a transformation script.

No such derivative was created during this release pass.
