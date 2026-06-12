# Phase Preflight Reference

Use this reference to scan later roadmap phases for prerequisites before Codex
automation reaches them.

## When To Run

Run phase preflight during setup before activating an automation, after a
permission-gated blocker, and before resuming a roadmap whose future phases
changed. The scan is read-only. It must not deliver future phases or mutate
saved automation configuration.

Use the helper from the repository root when available:

```bash
python3 skill/roadmap-delivery-skill/scripts/plan_phase_prerequisites.py \
  --repo-root <repo-root> \
  --roadmap-slug <roadmap-slug> \
  --automation-id <automation-id> \
  --json
```

To save durable evidence for the operator and later runs:

```bash
python3 skill/roadmap-delivery-skill/scripts/plan_phase_prerequisites.py \
  --repo-root <repo-root> \
  --roadmap-slug <roadmap-slug> \
  --automation-id <automation-id> \
  --output-json automation/<roadmap-slug>/phase_prerequisites.json \
  --output-markdown automation/<roadmap-slug>/phase_preflight.md
```

## Codex Checks

For each phase, inspect the phase body, `phase_model_policy.json`,
`approval_policy.json`, saved automation readback, and current environment.
Flag at least these categories:

- model or reasoning floors that the saved automation readback does not
  satisfy, including `high` readback when a later phase requires `xhigh`
- missing environment variables such as `OPENAI_API_KEY`, without printing
  secret values
- network/API requirements when `CODEX_SANDBOX_NETWORK_DISABLED=1`
- install/download/upload commands that need network access or approval
- `commit`, `push`, saved automation retarget, pause, promotion, publication,
  installed skill sync, credential use, and destructive git operations
- local tools that are not on `PATH`
- external account, billing, product, policy, or scope decisions

Use `approval_policy.json` to resolve every named operation to `allowed`,
`ask`, or `forbidden`. Missing policy falls back to conservative behavior, so a
later model retarget, local commit, push, or publication must be surfaced as a
future operator action instead of discovered only at the phase gate.

## Mitigation Format

Record each mitigation with enough detail for an operator to clear it before
activation:

- phase name or finalization
- blocker category and evidence
- required environment variable, tool, model/reasoning, network surface, or
  approval operation
- current readback or decision
- exact mitigation, such as setting `OPENAI_API_KEY` in the automation runtime,
  using a network-enabled runner, adding an offline fixture/dry-run acceptance
  path, or pre-approving `retarget_saved_automation`

For the common full extraction case, treat "OpenAI API", "full extraction
runner", or similar phase text as requiring both `OPENAI_API_KEY` and network
access unless the phase explicitly provides an offline fixture path. If the
current runtime has `CODEX_SANDBOX_NETWORK_DISABLED=1`, record a blocker and
recommend a network-enabled execution surface or an approved offline split.

## Host Adapter Boundary

Codex can inspect repository-local state, environment-variable presence, local
tool availability, and saved automation files under `~/.codex/automations` or
`AUTONOMOUS_ROADMAP_AUTOMATIONS_DIR`. It must not print secret values, edit
saved automation configuration, push branches, install global tools, or change
credentials during preflight.
