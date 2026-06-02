# Onboarding Wizard And Proof Demos Blocked Alert

Alert kind: `blocked`
Roadmap: `roadmaps/in_progress_onboarding_wizard_and_proof_demos_roadmap.md`
Phase: `Phase 2 - Wizard Implementation And Scaffold Integration`
Status: `blocked`
Reason: Current git branch is `main`, while delivery state expects `codex/onboarding-wizard-and-proof-demos-phase-2`; reflog shows `main` was fast-forwarded to the Phase 2 branch at 2026-06-02 11:18:48 +0100 without an approved promotion step.
Required model: `gpt-5.5`
Configured model: `gpt-5.5`
Required reasoning effort: `xhigh`
Configured reasoning effort: `xhigh`
Last verification: Phase 2 required verification passed before the branch/promotion blocker was recorded.
Last review: `automation/onboarding-wizard-and-proof-demos/reviews/onboarding-wizard-and-proof-demos-phase-2-review-iteration-1.md`
State file: `automation/onboarding-wizard-and-proof-demos/delivery_state.json`
Delivery log: `automation/onboarding-wizard-and-proof-demos/delivery_log.md`
Next human action: Decide whether to accept the fast-forwarded `main` state or approve a specific git repair path before Phase 2 resumes.

## Superseded

Superseded at: 2026-06-02T10:31:03Z
Superseded by: Operator asked to unblock the run; the already-fast-forwarded
`main` state was accepted as the human decision, and the active workflow was
switched back to `codex/onboarding-wizard-and-proof-demos-phase-2` without
destructive git.
