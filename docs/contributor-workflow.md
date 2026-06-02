# Contributor Workflow

Use this workflow when changing the framework, generated Codex package, docs,
or roadmap automation artifacts.

## Before Editing

1. Read the active roadmap phase and owned file list.
2. Read `automation/<roadmap-slug>/delivery_state.json`,
   `delivery_log.md`, `review_fix_state.json`, latest reviews, and
   `phase_model_policy.json` when present.
3. Read back the saved automation config when the run is automation-backed.
4. Check `git branch --show-current` and `git status --short --branch`.
5. Run artifact validation when state, branch, or review evidence might
   disagree.

Stop instead of guessing when the roadmap, state, log, review, branch,
worktree, or automation config disagree.

## Public Entry Points

Use structured public surfaces for contribution intake:

- Bug reports, installation help, roadmap requests, and documentation gaps live
  in `.github/ISSUE_TEMPLATE/`.
- Ideas, usage reports, and host compatibility observations live in
  `.github/DISCUSSION_TEMPLATE/` when GitHub Discussions is enabled.
- Pull requests use `.github/PULL_REQUEST_TEMPLATE.md` for scope,
  verification, privacy, adapter drift, release-impact, and support-boundary
  notes.
- Security concerns follow `SECURITY.md`; do not post exploit details or
  sensitive evidence in public threads.

Public issues, discussions, and pull requests must not include credentials,
private repository names, local home paths, `.codex` contents, local
automation logs, review transcripts, or unpublished release bundles. Redact
examples before sharing. The project does not provide guaranteed support
response times.

## Starter Tasks

Good starter work is local, reviewable, and does not require access to private
automation evidence:

- Improve wording in install docs, adapter docs, compatibility docs, or release
  notes.
- Add a small fixture for an existing CLI, schema, adapter, or privacy check.
- Clarify a roadmap acceptance criterion without adding committed dates or
  support promises.
- Reproduce an issue with a redacted local command transcript.
- Add a documentation cross-link that helps users find verification or privacy
  guidance.

Avoid starter tasks that require credentials, repository settings, publication,
installed-skill synchronization, private automation logs, or destructive git
operations.

## During Implementation

- Work on `codex/<roadmap-slug>-phase-<n>` for implementation phases.
- Change only files owned by the current phase plus required bookkeeping.
- Preserve unrelated worktree changes.
- Keep canonical workflow changes in `core/`, schema changes in `schemas/`,
  shared behavior in `src/roadmap_delivery/`, and host-specific package
  behavior in `adapters/<host>/`.
- Regenerate or check generated Codex package output with
  `scripts/build_codex_package.py --check`.

## Verification

Run every command named by the current phase. For broad framework changes, the
usual local gate is:

```bash
python3 -m unittest discover -s tests -v
python3 scripts/build_codex_package.py --check
python3 scripts/build_release.py --check
python3 scripts/check_release_privacy.py --repo-root .
git diff --check
```

Add targeted tests when behavior changes. Do not claim delivery if verification
only exercises pre-existing behavior.

## Review And Bookkeeping

Write a review artifact under
`automation/<roadmap-slug>/reviews/` with a verdict of `delivered`,
`needs-fix`, or `blocked`. Update delivery state, delivery log, review/fix
state, and progress tracking only after the review gate is satisfied.

Local commits should stage explicit paths only. Do not push, publish, sync the
installed Codex skill, merge to `main`, or edit live automation config unless
the operator explicitly approves that operation.

Public contribution threads should cite the relevant roadmap or issue, but
they should not copy local delivery state, automation alerts, review files, or
machine-specific paths into the public repository.
