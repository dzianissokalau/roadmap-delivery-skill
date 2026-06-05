# Changelog

All notable local framework release changes are recorded here.

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
