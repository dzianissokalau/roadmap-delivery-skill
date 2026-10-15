# Release Notes 0.3.0

Version `0.3.0` covers runtime reliability and portable installation. It changes
Python support to `>=3.12,<3.13`. The repository includes source-installable host
packages; a tagged release or registry upload is a separate publication step.
Whole-roadmap finalization and independent review require their own evidence.

## Highlights

- Shared control decisions give terminal handling precedence over phase/model
  gates. Matching operator activation and verified blocker repair are explicit.
- Verifier-backed semantic events and unique run IDs replace log fingerprint
  stall resets. Two consecutive unique no-progress outcomes pause by default.
- Completion/stall context opt-outs win in every approval mode. Status-only
  updates preserve other runner settings and need actual `PAUSED` readback.
- Interrupted alert/pause closeout resumes stable journal/effect IDs, rejects
  stale revisions and missing authority, and reports pending effects honestly.
- Codex/Claude packages carry stdlib runtime, schemas, metadata and integrity
  manifests. Directory and extracted-release helpers work outside the checkout
  with `-I -S`; local CLI installation uses explicit offline build prerequisites.
- Adaptive proposals obey model allowlists, reasoning floors/caps and provenance
  bindings. Exact legacy prompt upgrades use scoped authorization, verified
  readback and bounded rollback without changing unrelated settings.

## Regression Traceability

| Finding | Implementation | Executable evidence | Delivered review phases |
|---|---|---|---|
| R1: housekeeping reset stalls | `progress.py`, semantic journal | `test_progress_semantics`, extracted-release blocker churn/repair | 2, 8 |
| R2: installed helpers import checkout | bundled runtime/resources, package builders | `test_portable_install`, extracted-release missing-runtime probe | 4, 8 |
| R3: pause instructions and legacy saved prompts disagree | `control.py`, `approval.py`, `migrations.py`, shared references | `test_runtime_control`, `test_runtime_migrations`, legacy release scenario | 1, 3, 6, 7, 8 |
| R4: commented TOML duplicates status | `toml.py`, receipt-backed runner updates | `test_runner_updates`, release commented-status probe | 3, 8 |
| R5: delegated modes bypass opt-outs | context precedence in `approval.py` | `test_runtime_control`, all-mode release policy matrix | 1, 8 |
| R6: adaptive floor violated | `policy.py`, `adaptive.py`, shared planners | `test_model_target_constraints`, release floor/conflict probe | 5, 8 |

Module paths above refer to `src/roadmap_delivery/` and `tests/`. Six modeled old
behaviors fail at named regression probes; fixing wording alone is not the
closure evidence. Per-run command output, reviews, provenance and residual risks
belong in the local delivery evidence directory and are excluded from archives.

## Release Artifacts

`scripts/build_release.py` generates checksums; do not hardcode them in these
notes, which are themselves source-archive inputs.

| Artifact | Purpose |
|---|---|
| `roadmap-delivery-0.3.0-source.tar.gz` | Current filesystem source candidate. |
| `roadmap-delivery-codex-skill-0.3.0.tar.gz` | Complete portable Codex skill. |
| `roadmap-delivery-claude-plugin-0.3.0.tar.gz` | Complete local Claude plugin. |
| `roadmap-delivery-generic-markdown-pack-0.3.0.tar.gz` | Documentation-only future-adapter pack. |
| `roadmap-delivery-schemas-0.3.0.tar.gz` | Versioned schema bundle. |
| `roadmap-delivery-cli-0.3.0.tar.gz` | Offline-buildable CLI source. |
| `roadmap-delivery-0.3.0-manifest.json` | Identity, version, capability summary and hashes. |
| `roadmap-delivery-0.3.0-checksums.sha256` | SHA-256 verification list. |

## Local Verification

Run from the source checkout using Python 3.12:

```bash
python3.12 -m unittest discover -s tests -v
python3.12 scripts/build_adapters.py --check --json
python3.12 scripts/build_codex_package.py --check
python3.12 scripts/build_release.py --check --json
python3.12 scripts/check_release_privacy.py --repo-root .
git diff --check
python3.12 scripts/build_release.py --output-dir dist --json
```

From `dist/`, verify `shasum -a 256 -c roadmap-delivery-0.3.0-checksums.sha256`.
Rebuild after changing any source input. `docs/quickstart.md` supplies the clean
extracted-package first run; `docs/migration-guide.md` supplies upgrade planning,
scoped effects and recovery. Mandatory checks are offline and isolated.

Phase 8 evidence ran 360 tests (358 passed, two optional skips) and 230 raw
extracted-release driver calls. That is historical phase evidence; the candidate
requires its own fresh check output after final source changes. Failed development
attempts must remain distinguishable from the final passing receipts.

## Limitations

- Python 3.12 and cooperative POSIX directory locks are the verified runtime
  boundary. Windows, other Python minors and named live host versions are untested.
- The CLI build requires local setuptools>=68 and wheel; runtime execution has
  no third-party requirements. Damaged/mixed bundles need complete reinstallation.
- Offline scheduler doubles and synthetic review/authorization inputs establish
  contracts, not authentication, future model quality or live scheduler stopping.
  Independent agent evaluation and real scheduler effects were skipped in Phase 8.
  Binary help success cannot replace either. Remote CI needs separate run evidence.
- A skill upgrade leaves saved prompts unchanged. Unknown/custom prompts need a
  decision; a supported compare-and-set/idempotent adapter is required for effects.
- Same-context phase reviews remain explicitly limited. A prepared final prompt
  is neither an executed independent review nor a human waiver.
- The source archive excludes test/demo/CI fixtures. Reproduce the full suite
  from the repository checkout and retain its external candidate-bound receipts.
- The generic pack is documentation only; hooks add reminders/guards, without
  certifying permissions, secret detection, marketplace acceptance or host parity.

## Final Review Corrections

The 2026-10-15 correction set addresses all fifteen independent-review findings:
terminal recovery precedence, unreadable review evidence, recurring blocker
identity, retained adaptive evidence/capabilities, coherent quality run IDs,
bounded path-bound migrations, isolated version resolution, portable scaffold
commands, Claude hook interpreter/runtime boundaries, and current CI/docs pins.
Claude automatic hooks require `python3.12` on the host PATH; fail-closed
PreToolUse/UserPromptSubmit launch handling additionally requires v2.1.295+.
Offline regressions are not live scheduler or independent agent certification.

Fresh re-review also covers contradictory review verdicts, blockers discovered
during the last allowed run, damaged alerts, external execution acknowledgements,
retired migration authority, idempotent adaptive decisions, configured host
support, CLI metadata forwarding, partial plugin bundles and clean CI bootstrap.
External pause callers must record a request/attempt-bound outcome through
`terminal-closeout --external-outcome` before a retry can be reserved. Inspection
alone cannot reissue a pending request. See the finalization reference for the
outcome contract; PAUSED readback remains the only scheduler success evidence.

## Publication Boundary

Local preparation requires no credentials. Publication, tag/branch pushes,
promotion to main, marketplace submission, registry upload and global installed
skill/plugin synchronization require separate scoped human approval. Terminal
status-only completion/stall self-pause is the default policy exception unless
its context flag is false; confirmed receipt/readback remains mandatory.
