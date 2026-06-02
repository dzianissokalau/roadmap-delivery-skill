# Final Deep Review Prompt

Review the completed numbered phases for the Onboarding Wizard And Proof Demos
roadmap before finalization and human merge review.

Roadmap:
`roadmaps/delivered_onboarding_wizard_and_proof_demos_roadmap.md`

Automation:
`automation/onboarding-wizard-and-proof-demos/`

Expected local branch:
`codex/onboarding-wizard-and-proof-demos-finalization`

GitHub branch after publication:
`origin/codex/onboarding-wizard-and-proof-demos-finalization`

Repository:
`git@github.com:dzianissokalau/roadmap-delivery-skill.git`

Suggested external review target:
`https://github.com/dzianissokalau/roadmap-delivery-skill/tree/codex/onboarding-wizard-and-proof-demos-finalization`

Suggested compare base:
`origin/main`

## Reviewer Task

Use a skeptical code-review stance and lead with findings. Review the full
roadmap history, not only the latest Phase 5 diff.

Use these sources:

- roadmap header, phase objectives, acceptance criteria, non-goals, and stop
  conditions
- `automation/onboarding-wizard-and-proof-demos/delivery_state.json`
- `automation/onboarding-wizard-and-proof-demos/delivery_log.md`
- `automation/onboarding-wizard-and-proof-demos/review_fix_state.json`
- all review artifacts under
  `automation/onboarding-wizard-and-proof-demos/reviews/`
- `README.md`, `docs/quickstart.md`, `docs/who-this-is-for.md`,
  `docs/onboarding-wizard.md`, and `docs/evidence-benchmark.md`
- `examples/demo-roadmap/`, `examples/onboarding-wizard/`, and
  `examples/evidence-benchmark/`
- wizard, scaffold, validation, inspection, benchmark, privacy, adapter, and
  release verification evidence from the Phase 5 delivery log

## Questions To Answer

1. Can a new user follow one short safe path before configuring real
   automation?
2. Do wizard docs match the implemented generated files, JSON fields,
   validation readback, conflict behavior, and live-automation boundary?
3. Do the demo docs distinguish target users, non-target users, safe fixture
   demos, real automation setup, and optional host package installation?
4. Are benchmark claims tied to measured repository-local fixture results and
   limitations?
5. Do state, log, review files, roadmap header, model policy, approval policy,
   branch, saved automation readback, and worktree evidence agree?
6. Is verification sufficient for finalization and human merge review to begin?
7. Are publication, promotion, credential use, live automation edits,
   installed-skill sync, and destructive git still human-approved follow-ups?

## Required Output

Return:

- findings ordered by severity with file and line references where possible
- missing tests or checks
- state, log, branch, or review consistency gaps
- unresolved risks and promotion-readiness notes
- verdict: `ready-for-finalization`, `needs-fix`, or `blocked`

Do not approve publication, package release, promotion to `main`, branch push,
installed skill sync, credential use, saved automation pause, or destructive
git. Those remain separate human-approved operations.
