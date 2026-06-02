# Release Process

This process defines the release-readiness contract for Roadmap Delivery Skill.
It prepares a local release candidate and the evidence needed for operator
review. It does not publish tags, GitHub Releases, package registry uploads,
marketplace submissions, or installed skill updates.

## Release States

Use these terms consistently:

| State | Meaning | Allowed without publication approval |
|---|---|---|
| Local release candidate prepared | Release files are built locally from the repository, checksums exist, privacy checks pass, and evidence is recorded. | Yes |
| Published release | A tag, GitHub Release, package registry upload, marketplace submission, or external distribution channel has been updated. | No |

The automation may prepare and verify local artifacts when the roadmap phase
owns that work. A human must explicitly approve any step that changes an
external release surface, uses credentials, pushes a branch or tag, promotes to
`main`, syncs an installed global skill, or changes repository settings.

## Minimum Evidence Bundle

A release candidate is not ready for operator review until the evidence bundle
contains all of the following:

| Evidence | Expected source |
|---|---|
| Release notes | `docs/release-notes-0.1.0.md` or the current versioned notes file; this is the source of truth for contents, limitations, verification, and publication boundaries |
| Changelog entry | `CHANGELOG.md` entry matching `VERSION` |
| Release manifest | `dist/roadmap-delivery-<VERSION>-manifest.json` |
| SHA-256 checksums | `dist/roadmap-delivery-<VERSION>-checksums.sha256` |
| Adapter drift check | `python3 scripts/build_adapters.py --check` |
| Release artifact check | `python3 scripts/build_release.py --check` |
| Privacy scan | `python3 scripts/check_release_privacy.py --repo-root .` |
| Install smoke result | `python3 -m unittest tests.test_install_smoke -v` |
| Known limitations | Release notes and compatibility docs |
| Final closeout prompt | `automation/<roadmap-slug>/final-deep-review-prompt.md` |

The bundle may also include CI links, local command output summaries, or review
artifacts, but release archives themselves must not include `automation/`,
`roadmaps/`, `.git/`, `.codex/`, local alert files, review transcripts,
operator-specific state, credentials, or private local paths.

## Local Preparation Checklist

Before treating a local bundle as release-ready, run:

```bash
python3 scripts/build_adapters.py --check
python3 scripts/build_release.py --check --json
python3 scripts/check_release_privacy.py --repo-root .
python3 -m unittest tests.test_install_smoke -v
git diff --check
```

When bundle files are present under `dist/`, verify the checksums from inside
that directory:

```bash
shasum -a 256 -c roadmap-delivery-<VERSION>-checksums.sha256
```

For full release-candidate confidence, also run the repository test suite or
the release-check workflow equivalent documented in `README.md`.

## Release Candidate Closeout

Final closeout evidence must be recorded outside the release archives in the
roadmap delivery log, review artifact, and final deep-review prompt. The exact
artifact checksums should come from the generated manifest, checksum file, or
`scripts/build_release.py --check --json` output, not from hardcoded release
notes text. Release notes, the changelog, and README are part of the source
archive, so changing them after a checksum run requires rebuilding and
rechecking the candidate.

For the final automated closeout pass, run:

```bash
python3 -m unittest discover -s tests -v
python3 scripts/build_adapters.py --check --json
python3 scripts/build_release.py --check --json
python3 scripts/check_release_privacy.py --repo-root .
git diff --check
```

If ignored local files under `dist/` need to be refreshed for a human review,
build them locally with:

```bash
python3 scripts/build_release.py --output-dir dist --json
```

Refreshing local `dist/roadmap-delivery-*` files is still local preparation.
Publishing a tag, GitHub Release, package registry upload, marketplace
submission, release branch, installed skill, or live plugin sync remains
outside automation unless the operator explicitly approves that exact action.

## Privacy Gate

Release-bound content must pass the privacy scanner before any external copy or
publication. The scanner checks repository release paths and optional bundles
for local absolute paths, local temporary paths, obvious credential patterns,
private key markers, and forbidden bundle paths.

Use placeholders such as `/path/to/repo`, `$HOME`, `${CODEX_HOME}`, and
`<operator>` in examples. Do not publish automation state, local run logs,
review transcripts, alert files, private remotes, customer or operator names,
or credential-like values.

If the privacy scanner reports a finding, fix the source text or bundle input
and rebuild the candidate before review. Do not waive privacy findings from a
release archive unless a human explicitly approves the exact finding and the
release notes explain the residual risk.

## Host-Parity And Install Limits

Release guidance must keep compatibility claims tied to validated surfaces:

- Codex support is the generated package under `skill/roadmap-delivery-skill/`
  plus the documented install flow.
- Claude support is the generated local package under `dist/claude/` plus
  offline package, parity, hook, and smoke-test coverage.
- The generic markdown pack is a documentation template for future host
  planning, not a supported runtime integration.

Do not claim host vendor endorsement. Do not claim live host feature parity
unless the relevant smoke check has run and the result is recorded in the
evidence bundle. Keep optional live host checks separate from deterministic
local release gates.

## Publication Boundary

The following operations require explicit human approval even after every local
release gate passes:

- creating or pushing tags
- creating GitHub Releases
- uploading package registry artifacts
- submitting marketplace packages
- pushing release branches
- promoting changes to `main`
- using release credentials
- changing repository visibility, security, permissions, or billing
- syncing installed global Codex skills or host plugins

If a roadmap phase or automation run needs one of these operations to proceed,
stop and request the smallest specific approval. Record the prepared local
evidence and the blocked publication step in the delivery log rather than
performing the operation automatically.
