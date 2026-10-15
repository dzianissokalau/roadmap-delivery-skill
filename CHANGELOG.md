# Changelog

All notable local framework release changes are recorded here.

## 0.3.0 - 2026-10-14

Source version for runtime reliability and portable installation. Tagged release
and registry publication remain separate from source installation and review.

### Added

- Bundled stdlib runtime, schemas, version metadata and integrity manifests for
  Codex/Claude directory installs, extracted releases and offline CLI installs.
- Shared ordered control decisions, verifier-backed unique-run accounting,
  resumable alert/pause closeout and exact scoped saved-prompt migration.
- Extracted-release multi-project scenarios, six historical regression probes
  and crash recovery with persistent offline scheduler doubles.

### Fixed

- Log/timestamp/review churn cannot reset consecutive stalls. The second unique
  no-progress outcome triggers the default pause and preserves the blocker.
- Explicit completion/stall opt-outs override broad approval modes. Activation
  requires matching identity, model floor and prompt guards before phase work.
- TOML status updates preserve inline comments and unrelated settings without
  duplicate keys; scheduler acknowledgements alone do not prove a pause.
- Adaptive targets and persisted proposals obey model allowlists, reasoning
  floors/caps and evidence bindings on every resolution path.
- Final review fixes: completed scope cannot reopen through interrupted-run
  accounting; unreadable review evidence cannot prevent an authorized safety pause;
  recurring blockers receive distinct verifier-bound repair identities.
- Adaptive decisions retain source-run evidence and trusted model metadata
  throughout destination-phase verification. Missing run identity is not flawless.
- Policy-only migrations share retry/rollback guards, all migrations bind the
  real policy path, and no-effect verification requires fresh readback.
- Installed versions ignore ancestor project VERSION files; scaffold follow-up
  commands use the actual interpreter and installed entrypoint. Claude hooks no
  longer borrow checkout runtimes or use an ambiguous default Python executable.
- Independent re-review corrections reject quoted/contradictory verdicts, bind
  late-discovered blocker occurrences, recover damaged alerts, and require a
  bound host outcome before retrying an external pause request.
- Verified migration history survives failed rechecks and superseded authority
  cannot undo newer transactions. Adaptive retarget retries keep the same bound
  decision; configured targets must satisfy known host capabilities.
- CLI inspection forwards fresh capabilities. Partially damaged Claude bundles
  fail closed, generated runtimes are tracked, and CI provisions offline build
  prerequisites explicitly.

### Compatibility Notes

- Python support changes from the prior 3.9+ declaration to `>=3.12,<3.13`.
  Cooperative POSIX locks are required; Windows and other Python versions are
  untested. CLI builds additionally need local setuptools>=68 and wheel.
- Claude hooks require `python3.12` on the host PATH and Claude Code v2.1.295+
  for fail-closed launch/error handling on PreToolUse and UserPromptSubmit.
- Replace the complete skill/plugin package; a global install does not upgrade
  saved prompts. Prompt template 3, policy 2 and semantic evidence 1 are recorded
  separately from JSON artifact schema version 1.
- Legacy counters/history are retained. Unknown prompts, custom edits or missing
  authority need a scoped operator decision. Live scheduler/agent evaluation,
  publication, promotion and global synchronization are not implied by offline
  acceptance; binary help checks have a separate evidence category.

## 0.2.0 - 2026-06-05

Second local framework release candidate focused on user-ready setup,
automation lifecycle reliability, and distribution trust.

### Added

- Onboarding wizard, quickstart, fit guidance, and offline proof demos for
  first-use validation without live host mutation.
- Durable approval policy modes, adaptive model policy evidence, and default
  completion or stalled-run self-pause controls with saved automation readback.
- Release install and distribution trust documentation, local release process,
  privacy guardrails, public contribution surfaces, security policy, and
  trademark/licensing boundaries.
- Generated GitHub Action companion and optional host smoke harnesses for
  Codex and Claude, with skipped live checks kept separate from offline
  validation.
- Host capability metadata and compatibility docs for Codex, Claude, and the
  generic documentation pack.

### Fixed

- Lifecycle filename validation now catches active roadmaps that still use a
  `not_started_` prefix after Phase 0.
- Final roadmap closeout now requires a final deep review prompt or recorded
  human waiver before completion state is accepted.
- Saved automation activation is reconciled before generic mismatch blocking,
  so a user-started `ACTIVE` runner after paused setup does not waste a run or
  block delivery when model, cwd, prompt, and safety guards still match.
- Terminal completion and repeated-stall self-pause now remain allowed by
  default even when `approval_policy.json` is absent or a pause flag is
  missing; only an explicit `false` flag disables the default safety pause.
- Release and GitHub Action checks include portability fixes and stronger
  generated-package drift coverage.

### Compatibility Notes

- The project remains a local, file-backed, pre-1.0 framework. External
  publication, marketplace submission, installed skill synchronization,
  branch promotion, credentials, and destructive operations remain explicitly
  human-approved.
- `skill/roadmap-delivery-skill/` remains the installable Codex package path.
- `dist/claude/` remains the local Claude plugin package snapshot.
- Existing `0.1.0` release notes are retained as historical release-candidate
  documentation.

## 0.1.0 - 2026-06-02

Initial framework-core and multi-host adapter release candidate.

### Added

- Canonical workflow references, prompt fragments, and artifact templates.
- Versioned schemas for delivery state, model policy, review artifacts, and
  automation run logs.
- Shared `roadmap_delivery` Python helpers and a stable CLI.
- Generated Codex skill package checks backed by adapter snapshots.
- Generated Claude plugin package checks backed by adapter snapshots.
- Multi-host local release artifacts for Codex, Claude, schema, CLI, and the
  documentation-only generic markdown pack.
- CI, release-check, demo smoke, privacy, and release artifact gates.
- Deterministic local release artifacts with checksums and manifest metadata.
- Release candidate closeout guidance that ties release notes, changelog,
  manifest output, checksum output, privacy scans, adapter checks, install
  smoke checks, full test output, and final deep-review prompts together for
  human review.

### Compatibility Notes

- `skill/roadmap-delivery-skill/` remains the installable Codex package path.
- `dist/claude/` is the local Claude plugin package snapshot; live Claude Code
  loading remains an optional maintainer smoke check when the host binary is
  available.
- The generic markdown pack is documentation-only and does not claim support
  for future named hosts.
- Existing helper scripts under `skill/roadmap-delivery-skill/scripts/` remain
  compatibility wrappers.
- Legacy state artifacts continue to use warning-backed compatibility where the
  schema validators allow it.
- Publication to external release channels remains a separate human-approved
  action.

### Release Candidate Limitations

- Local release artifacts are preparation outputs, not a published release.
- Live Codex and Claude binary checks remain optional maintainer smoke checks
  when those host binaries are installed.
- The generic markdown pack remains documentation-only and does not claim
  runtime support for future named hosts.
- Marketplace submission, package registry upload, tag creation, branch push,
  installed-skill sync, live plugin sync, credentials, pricing, paid support,
  hosted-service packaging, and commercial terms are outside this release
  candidate.
