# Roadmap Automation Artifacts

This folder keeps low-level Codex delivery machinery separate from the
human-facing strategy and roadmap documents in `../roadmaps/`.

Use `../roadmaps/` for human-facing documents:

- `../roadmaps/automated-roadmap-delivery-strategy.md`
- `../roadmaps/delivered_autonomous-roadmap-delivery-skill-phased-roadmap.md`
- `../roadmaps/delivered_framework_core_and_release_readiness_roadmap.md`
- `../roadmaps/delivered_multi_host_adapter_and_claude_plugin_roadmap.md`
- `../roadmaps/delivered_autonomous_operation_modes_and_adaptive_control_roadmap.md`
- `../roadmaps/delivered_release_install_and_distribution_trust_roadmap.md`
- `../roadmaps/delivered_onboarding_wizard_and_proof_demos_roadmap.md`
- `../roadmaps/not_started_host_validation_and_github_action_companion_roadmap.md`

Use this folder for automation templates, state, logs, review outputs, and
closeout checklists.

## Layout

```text
automation/
  README.md
  codex_phase_gated_delivery_automation_template.md
  roadmap_closeout_checklist.md
  <roadmap_slug>/
    automation_guide.md
    approval_policy.json
    delivery_state.json
    delivery_log.md
    review_fix_state.json
    review_fix_log.md
    phase_model_policy.json
    automation_run_log.jsonl
    alerts/
    reviews/
      ...
```

Do not place delivery state, automation logs, or review iteration files directly
in the project root or `../roadmaps/`.

## Configured Roadmaps

| Roadmap | Status | Phase | Automation | State |
|---|---|---|---|---|
| `../roadmaps/delivered_autonomous-roadmap-delivery-skill-phased-roadmap.md` | Delivered | Complete | `autonomous-roadmap-delivery-skill` hourly, PAUSED | `autonomous-roadmap-delivery-skill/delivery_state.json` |
| `../roadmaps/delivered_phase_model_policy_and_stall_control_roadmap.md` | Delivered | Complete | `phase-model-policy-and-stall-control` hourly, PAUSED | `phase-model-policy-and-stall-control/delivery_state.json` |
| `../roadmaps/delivered_framework_core_and_release_readiness_roadmap.md` | Completed | Complete | `framework-core-and-release-readiness` hourly, PAUSED | `framework-core-and-release-readiness/delivery_state.json` |
| `../roadmaps/delivered_multi_host_adapter_and_claude_plugin_roadmap.md` | Completed | Complete | `multi-host-adapter-and-claude-plugin` hourly, PAUSED | `multi-host-adapter-and-claude-plugin/delivery_state.json` |
| `../roadmaps/delivered_autonomous_operation_modes_and_adaptive_control_roadmap.md` | Completed | Complete | `autonomous-operation-modes-and-adaptive-control` hourly, PAUSED | `autonomous-operation-modes-and-adaptive-control/delivery_state.json` |
| `../roadmaps/delivered_onboarding_wizard_and_proof_demos_roadmap.md` | Completed | Complete | `onboarding-wizard-and-proof-demos` hourly, PAUSED | `onboarding-wizard-and-proof-demos/delivery_state.json` |
| `../roadmaps/delivered_release_install_and_distribution_trust_roadmap.md` | Completed | Complete | `release-install-and-distribution-trust` hourly, PAUSED | `release-install-and-distribution-trust/delivery_state.json` |

## Planned Roadmaps

These roadmap documents exist in `../roadmaps/`, but no automation directory or
saved automation has been configured yet.

| Roadmap | Status | Suggested Slug |
|---|---|---|
| `../roadmaps/not_started_host_validation_and_github_action_companion_roadmap.md` | Not Started | `host-validation-and-github-action-companion` |

## Release Trust Roadmap Notes

`release-install-and-distribution-trust` is configured for phase-gated local
delivery. It may prepare release readiness evidence and repository-local docs,
but publishing tags, GitHub Releases, package registry uploads, marketplace
submissions, branch pushes, repository setting changes, credential use, and
installed-skill sync remain explicit human-approved operations.

## Migration Notes

Older automations without `approval_policy.json` remain valid in conservative
fallback mode. Add the policy file per automation, validate it, and then opt in
delegated operations only when the roadmap owner has approved that exact
surface. Inspect and validate reports show the effective autonomy mode,
approved operations, run quality, adaptive decision, and pause status so the
operator can distinguish legacy conservative behavior from malformed delegated
policy.
