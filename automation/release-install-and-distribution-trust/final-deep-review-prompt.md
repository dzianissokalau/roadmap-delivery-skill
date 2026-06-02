# Final Deep Review Prompt - Release Install And Distribution Trust

Roadmap:
`roadmaps/delivered_release_install_and_distribution_trust_roadmap.md`

Automation state:
`automation/release-install-and-distribution-trust/delivery_state.json`

GitHub review branch:
https://github.com/dzianissokalau/roadmap-delivery-skill/tree/codex/release-install-and-distribution-trust-phase-5

Direct GitHub prompt link:
https://github.com/dzianissokalau/roadmap-delivery-skill/blob/codex/release-install-and-distribution-trust-phase-5/automation/release-install-and-distribution-trust/final-deep-review-prompt.md

When reviewing from GitHub, resolve every repository-relative path below
against the review branch above. Treat that branch as review-only: do not infer
approval to merge, tag, publish, change repository settings, use credentials,
or sync installed tools.

Use this prompt in a fresh context before human merge review or any release
publication decision.

## Reviewer Task

Take a skeptical release-readiness review stance. Decide whether the delivered
roadmap is ready for human merge review and operator-approved publication
planning.

Review these artifacts:

- Roadmap delivery state, delivery log, review/fix state, review/fix log, and
  all phase review artifacts under
  `automation/release-install-and-distribution-trust/`.
- `docs/release-process.md`, `docs/release-notes-0.1.0.md`,
  `CHANGELOG.md`, `README.md`, `docs/installing-codex.md`,
  `docs/installing-claude.md`, `docs/adapters.md`,
  `docs/compatibility.md`, and `docs/trademark-and-licensing.md`.
- Generated Codex package snapshot under `skill/roadmap-delivery-skill/`.
- Generated Claude package snapshot under `dist/claude/`.
- Public contribution surfaces under `.github/`.
- Release builder, privacy scanner, adapter builder, and install smoke tests.

Check these questions:

- Do all roadmap phases have delivered review artifacts and passing required
  verification evidence?
- Do release notes, changelog, README, manifest/checksum output, and release
  process docs give a human enough information to review the first release
  candidate locally?
- Are release archives kept free of `automation/`, `roadmaps/`, `.git/`,
  `.codex/`, local alert files, review transcripts, private paths, and
  credentials?
- Do Codex and Claude package docs avoid vendor endorsement, unsupported host
  parity, marketplace availability, or installed package sync claims?
- Do public issue, discussion, and pull request templates discourage secrets,
  private paths, automation logs, review transcripts, and unpublished release
  bundles?
- Is publication still clearly blocked on explicit operator approval for tags,
  GitHub Releases, package registries, marketplace submissions, branch pushes,
  credentials, repository settings, and installed skill or plugin sync?
- Are commercialisation, pricing, paid support, hosted-service packaging, and
  guaranteed response times absent?
- Does the final state explain the pushed review branch, operator-paused saved
  automation, local completed alert, and remaining merge/publication approval
  boundaries?

Expected verification evidence:

```bash
python3 -m unittest discover -s tests -v
python3 scripts/build_adapters.py --check --json
python3 scripts/build_release.py --check --json
python3 scripts/check_release_privacy.py --repo-root .
git diff --check
python3 skill/roadmap-delivery-skill/scripts/validate_delivery_artifacts.py --repo-root . --roadmap-slug release-install-and-distribution-trust --automation-id release-install-and-distribution-trust --json
```

Return findings first, ordered by severity, with concrete file and line
references. Then report missing tests or checks, unresolved risks, and one of
these verdicts:

- `ready-for-human-merge-review`
- `needs-fix`
- `blocked`

Do not recommend publication, promotion to `main`, branch push, tag creation,
repository setting changes, credential use, or installed tool synchronization
unless the operator explicitly approves that separate action.
