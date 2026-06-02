# Delivery State Template

Use this template for `automation/<roadmap-slug>/delivery_state.json`.

```json
{
  "schema_version": 1,
  "roadmap": "roadmaps/<roadmap-file>.md",
  "roadmap_slug": "<roadmap-slug>",
  "current_phase": "Phase N - Name",
  "branch": "<phase-branch-or-null>",
  "status": "not_started",
  "review_iterations": 0,
  "max_review_iterations": 3,
  "last_verification": null,
  "last_review": null,
  "last_delivered_phase": null,
  "blocked_reason": null,
  "last_blocker_repair": null,
  "approval_policy_path": "automation/<roadmap-slug>/approval_policy.json",
  "approval_mode": "conservative",
  "last_approval_policy_readback": {
    "read_at": null,
    "path": "automation/<roadmap-slug>/approval_policy.json",
    "status": "valid",
    "approval_mode": "conservative",
    "approved_operations": [
      "edit_phase_owned_files",
      "write_state_log_review_artifacts",
      "create_or_switch_phase_branch",
      "run_verification"
    ],
    "pause_automation_on_completion": true,
    "pause_automation_on_stall": true,
    "fallback_reason": null
  },
  "required_model": "<required-model-or-null>",
  "required_reasoning_effort": "<required-reasoning-or-null>",
  "configured_automation_model": "<configured-model-or-null>",
  "configured_automation_reasoning_effort": "<configured-reasoning-or-null>",
  "run_count": 0,
  "stalled_run_count": 0,
  "max_stalled_runs": 2,
  "last_progress_signature": null,
  "last_progress_at": null,
  "last_operator_alert": null,
  "last_automation_pause": null,
  "last_run_quality": null,
  "last_adaptive_action": null,
  "model_history": [],
  "adaptive_escalation_count": 0,
  "adaptive_deescalation_count": 0,
  "adaptive_flawless_streak": 0,
  "auto_advance_after_delivered_review": true,
  "push_to_github": false,
  "all_phases_complete": false,
  "updated_at": null
}
```

Configured model and reasoning fields must come from runner readback, not from
desired policy values.

Wizard-generated starter state may temporarily record the selected local
runner target so repository-local validation can run before saved automation
creation. Replace those configured fields with saved runner readback before
activating scheduled delivery.

Missing `approval_policy.json` keeps legacy conservative behavior. Invalid
approval policies must fail validation before delivery relies on pre-approval.
