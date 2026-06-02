# Changelog

All notable local framework release changes are recorded here.

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
