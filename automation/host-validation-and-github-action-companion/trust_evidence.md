# Host Validation And GitHub Action Companion Trust Evidence

Generated: 2026-06-04T15:48:52Z
Roadmap: `roadmaps/delivered_host_validation_and_github_action_companion_roadmap.md`
Phase: Phase 6 - Trust Evidence Closeout
Branch: `codex/host-validation-and-github-action-companion-finalization`

## Evidence Surfaces

- GitHub Action companion:
  `.github/actions/roadmap-delivery-validate/action.yml` delegates offline
  validation to `python3 -m roadmap_delivery.cli github-action`.
- CI wiring: `.github/workflows/ci.yml` runs the local action with strict
  validation, adapter check, privacy scan, and review-evidence inspection.
- Release-check wiring: `.github/workflows/release-check.yml` runs the local
  action with release checks enabled before building local release artifacts.
- Optional host smoke harnesses: `scripts/host_smoke.py` supports Codex and
  Claude modes with `--isolated-home`; missing host binaries are reported as
  `skipped`.
- Optional host smoke workflow:
  `.github/workflows/host-smoke-nightly.yml` is `workflow_dispatch` only and
  writes raw host reports plus `host-smoke-reports/host-coverage.json`.
- Capability metadata: `host-capabilities/codex.yaml`,
  `host-capabilities/claude.yaml`, and `host-capabilities/generic.yaml` are
  the compatibility source of truth for live smoke status, skip visibility,
  fallback surfaces, and host parity boundaries.

## Live Host Check Record

- Real Codex live smoke: not run in Phase 6 because no explicit operator
  approval for live host execution or active host credentials was provided.
- Real Claude live smoke: not run in Phase 6 because no explicit operator
  approval for live host execution or active host credentials was provided.
- Skip semantics are verified by tests and targeted isolated-home smoke checks
  that use intentionally missing host binary paths; those checks do not touch
  active Codex or Claude configuration.

Targeted Phase 6 skip checks:

- `python3 scripts/host_smoke.py --host codex --isolated-home --codex-binary /private/tmp/roadmap-delivery-missing-codex --json`:
  `status: skipped`, `offline_status: passed`, `live_status: skipped`,
  reason `codex_binary_not_found`, `active_codex_home_used: false`,
  `created_real_automation: false`.
- `python3 scripts/host_smoke.py --host claude --isolated-home --claude-binary /private/tmp/roadmap-delivery-missing-claude --json`:
  `status: skipped`, `offline_status: passed`, `live_status: skipped`,
  reason `claude_binary_not_found`, `active_claude_config_used: false`,
  `created_real_automation: false`.

## False-Safety Boundary

- Offline CI validation can check roadmap state, review artifacts, adapter
  drift, privacy guardrails, release reproducibility, and declared capability
  metadata.
- Optional live host smoke checks can show that a narrow package or plugin path
  loads or runs under an available host surface.
- Neither surface proves marketplace acceptance, repository security,
  compliance, model quality, publication readiness, future host availability,
  or full runtime enforcement.

## Required Phase Verification

The Phase 6 gate records the exact command results in
`delivery_state.json` and `delivery_log.md`:

- `python3 -m unittest discover -s tests -v`
- `python3 scripts/build_adapters.py --check --json`
- `python3 scripts/build_release.py --check --json`
- `python3 scripts/check_release_privacy.py --repo-root .`
- `git diff --check`

## Human-Approved Follow-Ups

- Publishing a GitHub Marketplace Action.
- Enabling remote nightly workflow schedules.
- Creating repository secrets or authenticated host setup.
- Pushing branches, promoting to `main`, publishing release artifacts, or
  syncing installed global Codex or Claude packages.
