# Release Notes 0.1.0

Version `0.1.0` is the first local framework release candidate for Roadmap
Delivery Skill. It is buildable and verifiable from committed sources, but it
has not been published to an external package registry.

## Highlights

- Canonical workflow rules live under `core/references/`.
- Durable artifact templates and prompt guards live under `core/templates/`
  and `core/prompts/`.
- JSON schemas validate delivery state, phase model policy, review artifacts,
  and automation run logs.
- Shared Python helpers power inspection, validation, progress tracking, and
  CLI commands from `src/roadmap_delivery/`.
- `skill/roadmap-delivery-skill/` is a generated Codex package snapshot backed
  by adapter templates and drift checks.
- `dist/claude/` is a generated Claude plugin package snapshot with the main
  skill, reviewer agent, safety hooks, and canonical references.
- A documentation-only generic markdown pack is built for future adapter
  planning without claiming support for named hosts.
- CI and release-check workflows run local tests, package checks, schema
  checks, privacy scanning, and release reproducibility checks.
- `examples/demo-roadmap/` provides an offline fixture for smoke testing the
  workflow.
- `examples/autonomy-controls/` documents approval modes, adaptive retarget
  traces, and completion or stall self-pause evidence.

## Release Artifacts

These notes are the source of truth for the first release candidate contents.
`scripts/build_release.py` records matching package names, versions, SHA-256
checksums, and adapter capability summaries in
`dist/roadmap-delivery-0.1.0-manifest.json`.

The exact checksum values are generated output. They are intentionally kept in
the manifest, checksum file, and closeout evidence instead of being copied into
these notes, because these notes are included in the source archive and would
change the source checksum if edited after a build.

| Artifact | Purpose |
|---|---|
| `roadmap-delivery-0.1.0-source.tar.gz` | Repository source archive for local review. |
| `roadmap-delivery-codex-skill-0.1.0.tar.gz` | Generated Codex skill package. |
| `roadmap-delivery-claude-plugin-0.1.0.tar.gz` | Generated local Claude plugin package. |
| `roadmap-delivery-generic-markdown-pack-0.1.0.tar.gz` | Documentation-only pack for future adapter planning. |
| `roadmap-delivery-schemas-0.1.0.tar.gz` | Versioned schema bundle. |
| `roadmap-delivery-cli-0.1.0.tar.gz` | Local CLI source package. |
| `roadmap-delivery-0.1.0-manifest.json` | Deterministic manifest with package checksums and capability summaries. |
| `roadmap-delivery-0.1.0-checksums.sha256` | SHA-256 checksum file for local verification. |

## Local Verification

```bash
python3 -m unittest discover -s tests -v
python3 scripts/build_adapters.py --check
python3 scripts/build_release.py --check --json
python3 scripts/check_release_privacy.py --repo-root .
git diff --check
```

Final closeout also runs:

```bash
python3 -m unittest discover -s tests -v
```

After building into `dist/`, verify the local artifacts from inside that
directory:

```bash
shasum -a 256 -c roadmap-delivery-0.1.0-checksums.sha256
```

## Release Candidate Evidence

The first release candidate is ready for human review when the release
manifest, checksum output, adapter drift check, privacy scan, install smoke
checks, full test suite, and final deep-review prompt all exist and are
recorded in the roadmap delivery artifacts.

Evidence is split deliberately:

- User-facing release contents and limitations are in these notes and the
  changelog.
- Deterministic artifact identity is in the generated manifest and checksum
  output from `scripts/build_release.py`.
- Verification summaries, privacy scan results, and the final deep-review
  prompt are recorded under the roadmap automation artifacts.
- Publication, branch pushes, tag creation, marketplace submission,
  installed-skill sync, live plugin sync, and credential use remain outside
  the release candidate.

## Compatibility

- Existing Codex users can continue installing from
  `skill/roadmap-delivery-skill/`.
- Claude users can stage the generated local plugin package from
  `dist/claude/` or the local release artifact, but live Claude Code loading is
  still a maintainer smoke check when the host binary is available.
- The generic markdown pack is a planning artifact, not a supported runtime
  integration for future named hosts.
- Existing helper script paths remain available as wrappers.
- Legacy state artifacts remain supported where compatibility warnings are
  explicit.
- Existing automations without `approval_policy.json` remain conservative.
  Delegated local and delegated delivery modes require durable policy artifacts
  and readback evidence before saved automation retarget or pause actions.
- External publication, branch promotion, and installed-skill synchronization
  are not part of this release candidate and require operator approval.

## Limitations

- Release artifacts are local preparation outputs, not a published release.
- Live Codex and Claude binary checks are optional maintainer smoke checks when
  those host binaries are installed.
- The generic markdown pack is not a runtime integration for future named
  hosts.
- Marketplace submission, package registry upload, tag creation, and installed
  host sync are outside this release candidate.
- The final deep-review prompt prepares human or fresh-context review, but it
  does not publish or promote the release by itself.

## Publication Boundary

This release candidate can be built, checked, and reviewed locally without
credentials. Publishing a tag, GitHub Release, package registry artifact,
marketplace package, release branch, installed global skill, or live plugin
sync requires explicit human approval.

Commercialisation, pricing, paid support, hosted-service packaging, and
guaranteed response times are not part of this release candidate.
