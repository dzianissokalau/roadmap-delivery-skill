# Host Validation And GitHub Action Companion Deep Review Prompt

Review the Host Validation And GitHub Action Companion roadmap for final
acceptance and promotion readiness.

Repository:

- `https://github.com/dzianissokalau/roadmap-delivery-skill`

GitHub review target:

- Branch URL:
  `https://github.com/dzianissokalau/roadmap-delivery-skill/tree/codex/host-validation-and-github-action-companion-finalization`
- Deep-review prompt URL:
  `https://github.com/dzianissokalau/roadmap-delivery-skill/blob/codex/host-validation-and-github-action-companion-finalization/automation/host-validation-and-github-action-companion/deep_review_prompt.md`
- Raw prompt URL:
  `https://raw.githubusercontent.com/dzianissokalau/roadmap-delivery-skill/codex/host-validation-and-github-action-companion-finalization/automation/host-validation-and-github-action-companion/deep_review_prompt.md`
- Fetch commands:

```bash
git clone git@github.com:dzianissokalau/roadmap-delivery-skill.git
cd roadmap-delivery-skill
git fetch origin codex/host-validation-and-github-action-companion-finalization
git switch --detach FETCH_HEAD
```

Local review target:

- Branch: `codex/host-validation-and-github-action-companion-finalization`
- Roadmap:
  `roadmaps/delivered_host_validation_and_github_action_companion_roadmap.md`
- Delivery state:
  `automation/host-validation-and-github-action-companion/delivery_state.json`
- Delivery log:
  `automation/host-validation-and-github-action-companion/delivery_log.md`
- Review artifacts:
  `automation/host-validation-and-github-action-companion/reviews/`
- Trust evidence:
  `automation/host-validation-and-github-action-companion/trust_evidence.md`
- Completion alert:
  `automation/host-validation-and-github-action-companion/alerts/2026-06-04T16-07-22Z-completed.md`

Take a skeptical code-review stance. Lead with findings and cite file paths and
line numbers where possible.

Evaluate:

- Whether all roadmap phases are delivered or explicitly deferred.
- Whether roadmap, state, delivery log, review/fix state, reviews, model
  policy, approval policy, branch, and worktree evidence agree.
- Whether the GitHub Action companion validates roadmap delivery evidence in CI
  without requiring secrets, publication, or network-only behavior.
- Whether CI and release-check workflow wiring run the local action without
  leaking local automation evidence.
- Whether optional Codex and Claude host smoke checks remain opt-in, use
  isolated temporary homes, and report missing binaries as `skipped` rather
  than `passed`.
- Whether `docs/github-action.md`, `docs/host-smoke-checks.md`,
  `docs/compatibility.md`, host capability metadata, action outputs, and test
  assertions agree about live smoke status, host parity, fallback surfaces, and
  false-safety limits.
- Whether the final verification evidence is sufficient:
  `python3 -m unittest discover -s tests -v`,
  `python3 scripts/build_adapters.py --check --json`,
  `python3 scripts/build_release.py --check --json`,
  `python3 scripts/check_release_privacy.py --repo-root .`, and
  `git diff --check`.
- Whether publication, promotion to `main`, remote workflow scheduling,
  repository secret management, credential use, installed-skill sync, and
  installed-plugin sync remain safely human-approved.
- Whether finalization correctly renamed the roadmap to `delivered_...`,
  wrote the completion alert, and handled automation pause without losing
  evidence or bypassing approval policy.

Output:

- Findings ordered by severity.
- Missing tests or missing checks.
- State/log/review consistency issues.
- Residual risks.
- Promotion readiness recommendation.
- Verdict: `ready-for-human-review`, `needs-fix`, or `blocked`.
