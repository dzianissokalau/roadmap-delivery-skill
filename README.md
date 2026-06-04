# Roadmap Delivery Skill

Roadmap Delivery Skill is a file-backed, phase-gated delivery framework for
roadmap-driven coding work. The repository now separates the canonical workflow
core from host-specific packaging, with supported Codex and Claude packages plus
a generic markdown pack for future adapter planning.

GitHub repository: `git@github.com:dzianissokalau/roadmap-delivery-skill.git`

[![CI](https://github.com/dzianissokalau/roadmap-delivery-skill/actions/workflows/ci.yml/badge.svg)](https://github.com/dzianissokalau/roadmap-delivery-skill/actions/workflows/ci.yml)
[![Release Check](https://github.com/dzianissokalau/roadmap-delivery-skill/actions/workflows/release-check.yml/badge.svg)](https://github.com/dzianissokalau/roadmap-delivery-skill/actions/workflows/release-check.yml)

Key docs:

- Adapters: `docs/adapters.md`
- Architecture: `docs/architecture.md`
- Autonomy and approval policy: `docs/autonomy-and-approval-policy.md`
- Compatibility: `docs/compatibility.md`
- Contributor workflow: `docs/contributor-workflow.md`
- Evidence benchmark contract: `docs/evidence-benchmark.md`
- GitHub Action contract: `docs/github-action.md`
- Host smoke check boundary: `docs/host-smoke-checks.md`
- Codex install: `docs/installing-codex.md`
- Claude install: `docs/installing-claude.md`
- Migration guide: `docs/migration-guide.md`
- Onboarding quickstart: `docs/quickstart.md`
- Onboarding wizard contract: `docs/onboarding-wizard.md`
- Privacy and release sanitization: `docs/privacy-and-sanitization.md`
- Release process: `docs/release-process.md`
- Release notes: `docs/release-notes-0.1.0.md`
- Security policy: `SECURITY.md`
- Trademark and licensing: `docs/trademark-and-licensing.md`
- Who this is for: `docs/who-this-is-for.md`

## Quickstart

For a first-use path that starts with the safe demo fixture and then moves to a
real-project scaffold dry run, use `docs/quickstart.md`. For fit guidance, use
`docs/who-this-is-for.md`.

Recommended first-use order:

1. Read `docs/who-this-is-for.md` to check fit and non-fit cases.
2. Run the safe demo path in `docs/quickstart.md`; it uses local fixtures and
   temporary homes before any real project setup.
3. Inspect `examples/demo-roadmap/README.md` for the normal evidence trail and
   the policy-mismatch recovery demo.
4. Preview starter artifacts with `python3 -m roadmap_delivery.cli wizard
   --dry-run --json` or the recipes in `examples/onboarding-wizard/README.md`.
5. Use the real-project scaffold or wizard write mode only after reviewing the
   generated approval policy, model policy, state, log, and validation output.

The benchmark proof is local too:

```bash
python3 -m roadmap_delivery.cli benchmark \
  --repo-root . \
  --json \
  --output /tmp/roadmap-delivery-evidence-benchmark.json
```

It reports fixture evidence quality and invalid-advancement detection without
claiming productivity, ROI, compliance, model speed, or vendor comparisons.

### Install In Codex

The installable Codex skill package is committed in this repository:

```text
skill/roadmap-delivery-skill/
```

Install it from inside Codex first:

1. Open Codex and ask:

   ```text
   Install the Codex skill from GitHub repo dzianissokalau/roadmap-delivery-skill at path skill/roadmap-delivery-skill
   ```

2. Approve the install if Codex asks for confirmation.
3. Restart Codex if prompted.

If your Codex build has a Skills or Plugins import screen, use the same values:

- Repository: `dzianissokalau/roadmap-delivery-skill`
- Skill path: `skill/roadmap-delivery-skill`

This repository ships the generated skill package, so users do not need to run
the renderer before installing it.

After restart, try:

```text
$roadmap-delivery-skill inspect this roadmap automation state
```

### CLI Install Fallback

If the in-Codex install path is unavailable or you are scripting setup, use
Codex's bundled skill installer:

```bash
python3 "$HOME/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py" \
  --repo dzianissokalau/roadmap-delivery-skill \
  --path skill/roadmap-delivery-skill
```

This installs to:

```text
${CODEX_HOME:-$HOME/.codex}/skills/roadmap-delivery-skill
```

Restart Codex after installation so the skill is picked up.

Manual fallback:

```bash
git clone git@github.com:dzianissokalau/roadmap-delivery-skill.git /tmp/roadmap-delivery-skill
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
cp -R /tmp/roadmap-delivery-skill/skill/roadmap-delivery-skill \
  "${CODEX_HOME:-$HOME/.codex}/skills/"
```

To verify the generated package before installing:

```bash
python3 scripts/build_codex_package.py --check
python3 -m unittest tests.test_adapter_codex -v
```

### Developer Setup

Run the framework from a checkout:

```bash
python3 -m roadmap_delivery.cli version

python3 -m roadmap_delivery.cli inspect \
  --repo-root "$PWD" \
  --roadmap-slug framework-core-and-release-readiness \
  --automation-id framework-core-and-release-readiness \
  --json

python3 -m roadmap_delivery.cli validate \
  --repo-root "$PWD" \
  --roadmap-slug framework-core-and-release-readiness \
  --automation-id framework-core-and-release-readiness \
  --strict \
  --allow-warning worktree_dirty \
  --json
```

Install the local Python package when you want the `roadmap-delivery` console
script during development:

```bash
python3 -m pip install -e .
roadmap-delivery version
```

## Architecture

The repository is organized around durable files rather than a service-backed
control plane:

| Surface | Path | Responsibility |
|---|---|---|
| Core workflow | `core/references/` | Host-neutral setup, delivery, review, state, finalization, and troubleshooting rules. |
| Templates and prompts | `core/templates/`, `core/prompts/` | Reusable state, log, review, prompt, and guard text. |
| Schemas | `schemas/` | Versioned contracts for delivery state, model policy, approval policy, provider config, reviews, and run logs. |
| Shared library | `src/roadmap_delivery/` | Validation, inspection, approval policy, adaptive model policy, alerts, automation helpers, progress, git, state, and CLI behavior. |
| Codex adapter | `adapters/codex/` | Rendering inputs for the committed Codex skill package. |
| Codex package | `skill/roadmap-delivery-skill/` | Generated installable skill snapshot and compatibility scripts. |
| Claude adapter | `adapters/claude/` | Rendering inputs for the committed local Claude plugin package. |
| Claude package | `dist/claude/` | Generated local Claude plugin snapshot with skill, reviewer agent, hooks, and references. |
| Generic adapter | `adapters/generic/` | Documentation and schema pack for future host planning. |
| Automation evidence | `automation/<roadmap-slug>/` | Local state, logs, alerts, reviews, and guide files for roadmap runs. |
| Release artifacts | `dist/roadmap-delivery-*` | Ignored local release bundles, manifest, and checksums created by `scripts/build_release.py`. |

The Codex package and Claude plugin are generated from canonical core sources
plus host adapter overlays. `scripts/build_adapters.py --check` fails when the
committed package snapshots drift from those inputs, while
`scripts/build_codex_package.py --check` remains a compatibility wrapper for the
Codex package.

## Compatibility Matrix

| Surface | Current support | Notes |
|---|---|---|
| Codex skill path | Supported | `skill/roadmap-delivery-skill/` remains installable. |
| Legacy helper script paths | Supported | Scripts under `skill/roadmap-delivery-skill/scripts/` are compatibility wrappers. |
| Python CLI | Supported | Use `python3 -m roadmap_delivery.cli` from a checkout or `roadmap-delivery` after install. |
| State schema | Versioned | `schema_version: 1` is validated; legacy states remain warning-backed where supported. |
| Model policy | Supported | `phase_model_policy.json` gates required model and reasoning readback. |
| Approval policy | Supported | `approval_policy.json` selects conservative, delegated, or custom operation permissions. Missing policy falls back to conservative behavior. |
| Adaptive model policy | Supported | Run quality can retarget the next run within explicit policy caps and saved automation readback. |
| Provider role config | Supported example | `config/providers.example.yaml` documents reusable role-to-model mappings; runner readback remains authoritative. |
| Completion and stall self-pause | Default safety behavior | Generated policies pause completed automations and pause stalled automations after 2 no-progress runs by default, with opt-out policy flags and saved automation readback. |
| Adapter generation | Supported | `scripts/build_adapters.py --check` verifies committed Codex and Claude output. |
| Release artifacts | Local only | Build and verify locally; publication requires explicit human approval. |
| GitHub Action companion | Supported local action | `.github/actions/roadmap-delivery-validate` delegates to the CLI, adapter check, privacy scan, release check, and review-evidence inspection without requiring secrets. |
| Live host smoke checks | Supported optional evidence | `scripts/host_smoke.py` and the dispatch-only host smoke workflow keep Codex and Claude live status separate from offline validation and preserve skipped results. |
| Nightly host smoke workflow | Opt-in template | `.github/workflows/host-smoke-nightly.yml` is manual-dispatch by default; scheduling or authenticated host setup remains human-approved. |
| Claude adapter | Supported locally | Generated Claude plugin package, reviewer agent, hooks, install docs, and offline smoke tests ship as local release artifacts; live Claude binary checks remain optional. |
| Generic markdown pack | Documentation template | Built only as an explicit release artifact for future adapter planning. |
| Hosted control plane | Not included | This roadmap keeps state, logs, reviews, and alerts file-backed. |

## Roadmaps

| Status | Roadmap | Public summary |
|---|---|---|
| Delivered | `roadmaps/delivered_autonomous-roadmap-delivery-skill-phased-roadmap.md` | Original Codex roadmap and repository skill snapshot. |
| Delivered | `roadmaps/delivered_phase_model_policy_and_stall_control_roadmap.md` | Model-aware automation retargeting, stalled-run handling, and local operator alerts. |
| Delivered | `roadmaps/delivered_framework_core_and_release_readiness_roadmap.md` | Framework hardening for the canonical core, schemas, shared library, CLI, generated Codex adapter, CI, privacy, release, and closeout. |
| Delivered | `roadmaps/delivered_multi_host_adapter_and_claude_plugin_roadmap.md` | Companion roadmap for generated host adapters and Claude packaging; the saved automation is paused. |
| Delivered | `roadmaps/delivered_autonomous_operation_modes_and_adaptive_control_roadmap.md` | Autonomy modes, adaptive model escalation, and automatic pause behavior; the saved automation is paused. |
| Delivered | `roadmaps/delivered_onboarding_wizard_and_proof_demos_roadmap.md` | Setup wizard generation, golden-path demos, quickstart fit guidance, and measurable delivery-evidence proof; the saved automation is paused. |
| Delivered | `roadmaps/delivered_release_install_and_distribution_trust_roadmap.md` | First tagged release readiness, install and distribution trust, licensing/trademark guidance, marketplace-native preparation, public governance surfaces, and local closeout evidence. |
| Delivered | `roadmaps/delivered_host_validation_and_github_action_companion_roadmap.md` | Optional live host smoke checks, capability metadata, and a GitHub Action validation or review-evidence companion; final evidence is recorded and the saved automation is paused. |

Roadmap status describes local delivery evidence only. It does not promise
delivery dates, paid support, hosted services, marketplace acceptance, or
publication.

## Public Contribution Entry Points

Use the repository templates for public-safe contributions:

- Bug reports, installation help, roadmap requests, and documentation gaps use
  `.github/ISSUE_TEMPLATE/`.
- Ideas, usage reports, and host compatibility observations use
  `.github/DISCUSSION_TEMPLATE/` when GitHub Discussions is enabled.
- Pull requests should use `.github/PULL_REQUEST_TEMPLATE.md` and include
  verification, privacy, adapter drift, and release-impact notes.
- Security or vulnerability details should follow `SECURITY.md` and should not
  be posted in public issues or discussions.

Do not post credentials, private paths, local automation logs, review
transcripts, or unpublished release bundles in public contribution surfaces.
The project does not provide guaranteed response times.

## Operating Model

Roadmap delivery uses a single-phase loop:

1. Reconcile the roadmap, state, log, reviews, model policy, saved automation
   config, branch, and worktree before editing.
2. Deliver exactly one current phase on `codex/<roadmap-slug>-phase-<n>`.
3. Run every required verification command plus targeted checks for changed
   behavior.
4. Write a skeptical review artifact with verdict `delivered`, `needs-fix`, or
   `blocked`.
5. Advance state only after acceptance criteria, verification, and review all
   agree.
6. Preserve publication, promotion, installed-skill sync, destructive git, and
   credential use as explicit human-approved actions.

Completed roadmaps hard-stop before new phase work. When approval policy or an
explicit operator decision allows it, the framework can pause a saved automation
and record readback evidence. Otherwise, the local completion alert is the
durable fallback and the pause remains a human-approved operation.

## Autonomy Controls

Autonomy is selected per roadmap automation with `approval_policy.json`.
Existing automations without that file stay conservative: they may edit
phase-owned files, write state/log/review artifacts, create or switch the
current phase branch, and run verification. Retargeting saved automation
model/reasoning, pausing a saved automation, committing locally, pushing a
branch, publication, promotion, credential use, installed-skill sync, and
destructive git remain approval-gated unless a durable policy explicitly allows
the lower-risk operation.

Use these files when choosing a mode:

- `docs/autonomy-and-approval-policy.md`: policy contract and operation table.
- `docs/migration-guide.md`: opt-in steps for existing automations.
- `examples/autonomy-controls/`: approval policy examples, adaptive model
  trace, and completion/stall pause examples.
- `examples/demo-roadmap/scenarios/delegated-local/approval_policy.json`: demo
  fixture for inspecting delegated local decisions without live automation
  changes.

Never-auto operations remain forbidden in every mode: force push,
`git reset --hard`, branch or tag deletion, promotion to `main`, release or
package publication, unavailable credential use, repository security or billing
changes, global tool sync, and destructive filesystem operations outside phase
scope.

## Framework CLI

The shared package exposes stable inspection, validation, scaffold, package,
and version commands:

```bash
python3 -m roadmap_delivery.cli version

python3 -m roadmap_delivery.cli inspect \
  --repo-root "$PWD" \
  --roadmap-slug framework-core-and-release-readiness \
  --automation-id framework-core-and-release-readiness \
  --json

python3 -m roadmap_delivery.cli validate \
  --repo-root "$PWD" \
  --roadmap-slug framework-core-and-release-readiness \
  --automation-id framework-core-and-release-readiness \
  --strict \
  --allow-warning worktree_dirty \
  --json

python3 -m roadmap_delivery.cli scaffold \
  --repo-root "$PWD" \
  --roadmap-slug example-roadmap \
  --automation-id example-roadmap-delivery \
  --dry-run \
  --json

python3 -m roadmap_delivery.cli package \
  --repo-root "$PWD" \
  --adapter codex \
  --dry-run \
  --json
```

After installation, the same interface is available as `roadmap-delivery`.
The legacy helper scripts under `skill/roadmap-delivery-skill/scripts/` call
the same shared library paths.

## Demo Fixture

`examples/demo-roadmap/` is a self-contained fixture for trying the workflow
without network access, credentials, or live Codex app automation. It includes
a three-phase demo roadmap, state/log/review artifacts, a model policy, an
approval-policy scenario, and scenarios for blocked remediation and
model-policy mismatch.

```bash
python3 -m roadmap_delivery.cli scaffold \
  --repo-root /tmp/demo-roadmap-plan \
  --roadmap-slug demo-roadmap \
  --automation-id demo-roadmap-delivery \
  --dry-run \
  --json

python3 -m roadmap_delivery.cli validate \
  --repo-root examples/demo-roadmap \
  --roadmap-slug demo-roadmap \
  --json

python3 -m roadmap_delivery.cli inspect \
  --repo-root examples/demo-roadmap \
  --roadmap-slug demo-roadmap \
  --json
```

The smoke tests copy the fixture to a temporary git repository and temporary
home directory so automation readback and blocker behavior can be exercised
without touching a real saved Codex automation.

## CI And Release Checks

GitHub Actions run repository-local checks only. The optional Codex skill
validator runs only when `CODEX_QUICK_VALIDATE` points at an available
`quick_validate.py` script, so CI does not require private Codex directories or
credentials.

The local GitHub Action companion is documented in `docs/github-action.md` and
is wired into CI and release-check workflows. Its default contract is offline
validation that delegates to the existing CLI and helper scripts. Optional
live Codex or Claude smoke checks are documented separately in
`docs/host-smoke-checks.md` and exposed through a dispatch-only workflow; they
must be explicitly enabled and must report missing prerequisites as skipped,
not passed.

Local equivalents for the CI workflow:

```bash
python3 -m unittest discover -s tests -v

PYTHONPYCACHEPREFIX="${TMPDIR:-/tmp}/roadmap-delivery-ci-pycache" \
  python3 -m py_compile \
  scripts/build_codex_package.py \
  scripts/build_release.py \
  scripts/check_release_privacy.py \
  src/roadmap_delivery/*.py \
  roadmap_delivery/__init__.py \
  skill/roadmap-delivery-skill/scripts/*.py \
  tests/*.py

python3 -m unittest tests.test_schema_validation -v
python3 scripts/build_adapters.py --check
python3 scripts/build_codex_package.py --check
python3 -m unittest tests.test_quality_gates -v
python3 -m unittest tests.test_smoke_demo -v
python3 scripts/check_release_privacy.py --repo-root .

python3 -m roadmap_delivery.cli validate \
  --repo-root "$PWD" \
  --roadmap-slug framework-core-and-release-readiness \
  --automation-id framework-core-and-release-readiness \
  --strict \
  --allow-warning missing_automation_config \
  --allow-warning current_branch_name_mismatch \
  --allow-warning worktree_dirty \
  --json

git diff --check

if [ -n "${CODEX_QUICK_VALIDATE:-}" ] && [ -f "${CODEX_QUICK_VALIDATE}" ]; then
  python3 "${CODEX_QUICK_VALIDATE}" skill/roadmap-delivery-skill
fi
```

## Release Artifacts

The repository release version is stored in `VERSION`. The Python package
metadata stays unpublished until a separate publication phase, so local
release artifacts use `VERSION` for archive names, manifests, and checksums.
Use `docs/release-process.md` as the release-readiness checklist and as the
boundary between a local release candidate and a published release.
Exact checksum values are generated output and belong in the manifest,
checksum file, and roadmap closeout evidence; do not hardcode them into docs
that are included in the source archive.

`scripts/build_release.py` builds these deterministic local artifacts:

- source archive
- Codex skill package
- Claude plugin package
- schema bundle
- CLI source package
- generic markdown pack for future adapter planning
- release manifest
- SHA-256 checksum file

Local equivalent for the release-check artifact build:

```bash
python3 scripts/build_release.py --check
python3 scripts/build_release.py --output-dir dist --json
(cd dist && shasum -a 256 -c roadmap-delivery-0.1.0-checksums.sha256)
python3 scripts/check_release_privacy.py --repo-root . \
  --bundle dist/roadmap-delivery-0.1.0-source.tar.gz \
  --bundle dist/roadmap-delivery-codex-skill-0.1.0.tar.gz \
  --bundle dist/roadmap-delivery-claude-plugin-0.1.0.tar.gz \
  --bundle dist/roadmap-delivery-schemas-0.1.0.tar.gz \
  --bundle dist/roadmap-delivery-cli-0.1.0.tar.gz \
  --bundle dist/roadmap-delivery-generic-markdown-pack-0.1.0.tar.gz
```

Release links:

- Changelog: `CHANGELOG.md`
- Release notes: `docs/release-notes-0.1.0.md`
- Release check workflow:
  `https://github.com/dzianissokalau/roadmap-delivery-skill/actions/workflows/release-check.yml`

Rollback is file-backed: keep the previous `VERSION`, changelog entry, and
checksum file together, rebuild from that commit, and reinstall the prior
`skill/roadmap-delivery-skill/` package if an operator needs to revert a local
Codex installation. Do not publish GitHub Releases, PyPI packages, Homebrew
formulae, or other external artifacts without explicit approval.

## Contributor Workflow

Use `docs/contributor-workflow.md` for the full workflow. The short form is:
pick the current roadmap phase, verify the owned file list, keep changes
phase-scoped, run required checks, write review evidence, and avoid publishing
or syncing installed skills without explicit approval.

## Migration Guide

Use `docs/migration-guide.md` when moving an existing Codex-only automation to
the framework layout. The migration keeps `skill/roadmap-delivery-skill/`
installable while moving source-of-truth behavior into `core/`, `schemas/`,
`src/roadmap_delivery/`, and adapter templates.

## License

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE). Generated
package snapshots and local release archives use the same project license unless
a file says otherwise. Vendor names are used only as compatibility labels; see
`docs/trademark-and-licensing.md` for package and endorsement boundaries.
