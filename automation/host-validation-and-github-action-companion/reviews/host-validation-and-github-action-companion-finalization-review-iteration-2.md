# Finalization Review - Iteration 2

Roadmap:
`roadmaps/delivered_host_validation_and_github_action_companion_roadmap.md`
Phase: post-finalization external review repair
Reviewed at: 2026-06-04T17:38:25Z
Branch: `codex/host-validation-and-github-action-companion-finalization`
Verdict: delivered

## Findings

- [P2] `.github/actions/roadmap-delivery-validate/action.yml:123` previously
  used Bash 4 lowercase expansion `${1,,}` in the composite action `truthy`
  helper. That fails with `bad substitution` on Bash 3.2, including common
  macOS/self-hosted runner environments. The helper now uses `printf` plus
  `tr '[:upper:]' '[:lower:]'` normalization at
  `.github/actions/roadmap-delivery-validate/action.yml:125`, which preserves
  the documented truthy values without requiring Bash 4.

## Missing Tests Or Checks

- None for the reported portability issue. `tests/test_github_action.py:126`
  now asserts the action no longer contains `${1,,}` and requires the portable
  `printf` plus `tr` normalization path.
- A local `/bin/bash` 3.2.57 smoke confirmed the helper accepts `TRUE`, `Yes`,
  and `on`, and rejects `false`.

## Finding Disposition

- [P2] Bash 3.2-incompatible lowercase expansion in the composite action:
  fixed.

## Verification

- `python3 -m unittest tests.test_github_action -v`: passed, 7 tests.
- `/bin/bash --version`: passed, confirmed GNU Bash 3.2.57.
- `/bin/bash -c 'set -euo pipefail; truthy(){ ... }; truthy TRUE; truthy Yes; truthy on; ! truthy false'`:
  passed.
- `git diff --check`: passed.
- `PYTHONPATH=src python3 -m roadmap_delivery.cli validate --repo-root . --roadmap-slug host-validation-and-github-action-companion --automation-id host-validation-and-github-action-companion --allow-warning worktree_dirty --json`:
  passed with only the expected dirty-worktree warning while the repair was
  uncommitted.

## Residual Risks

- Same-context review was used because no separate reviewer context is
  available in this automation run.
- The repository's checked-in workflows target `ubuntu-latest`; this repair
  covers the documented general GitHub Actions checkout and self-hosted runner
  portability path without adding a live macOS CI job.
- Release publication, remote schedule activation, repository secrets,
  credentials, and installed package synchronization remain separate
  human-approved actions.

## Verdict

delivered
