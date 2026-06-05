# Release Notes 0.2.0

Version `0.2.0` is the second local framework release candidate for Roadmap
Delivery Skill. It remains a pre-1.0, file-backed workflow package that can be
built and verified from committed sources, but it has not been published to an
external package registry or marketplace.

## Highlights

- The onboarding wizard, quickstart, fit guidance, and proof demos make the
  first-use path testable without live Codex or Claude configuration changes.
- Durable approval policy modes define conservative, delegated local,
  delegated delivery, and custom operation boundaries.
- Adaptive model policy records run quality and can retarget the next saved
  automation run within explicit policy caps and readback checks.
- Completion and stalled-run self-pause are default safety behaviors for
  generated policies, with local alert fallbacks when saved automation pause is
  unavailable, explicitly disabled, or readback cannot prove `PAUSED`.
- Missing approval policy artifacts no longer turn terminal self-pause into a
  human-approval blocker; completion and repeated-stall pause remain allowed by
  default unless a context flag is explicitly `false`.
- Setup reconciliation now treats an operator-started `ACTIVE` automation
  after paused setup as normal activation when model, reasoning, cwd, prompt,
  and safety guards still match.
- Lifecycle and finalization gates now cover active roadmaps that retain
  `not_started_` filenames and completed roadmaps that lack a final deep
  review prompt or recorded waiver.
- Release install and distribution trust docs now cover privacy scanning,
  public contribution surfaces, security policy, trademark and licensing
  boundaries, and publication limits.
- A local GitHub Action companion delegates offline validation, adapter drift,
  privacy, release, and review-evidence checks to the repository CLI and
  helper scripts.
- Optional Codex and Claude host smoke checks provide maintainer evidence while
  keeping skipped live checks separate from offline validation success.
- Host capability metadata records Codex, Claude, and generic adapter support
  claims alongside explicit fallbacks.

## Release Artifacts

These notes are the source of truth for the `0.2.0` local release candidate
contents. `scripts/build_release.py` records matching package names, versions,
SHA-256 checksums, and adapter capability summaries in
`dist/roadmap-delivery-0.2.0-manifest.json`.

The exact checksum values are generated output. They are intentionally kept in
the manifest, checksum file, and closeout evidence instead of being copied into
these notes, because these notes are included in the source archive and would
change the source checksum if edited after a build.

| Artifact | Purpose |
|---|---|
| `roadmap-delivery-0.2.0-source.tar.gz` | Repository source archive for local review. |
| `roadmap-delivery-codex-skill-0.2.0.tar.gz` | Generated Codex skill package. |
| `roadmap-delivery-claude-plugin-0.2.0.tar.gz` | Generated local Claude plugin package. |
| `roadmap-delivery-generic-markdown-pack-0.2.0.tar.gz` | Documentation-only pack for future adapter planning. |
| `roadmap-delivery-schemas-0.2.0.tar.gz` | Versioned schema bundle. |
| `roadmap-delivery-cli-0.2.0.tar.gz` | Local CLI source package. |
| `roadmap-delivery-0.2.0-manifest.json` | Deterministic manifest with package checksums and capability summaries. |
| `roadmap-delivery-0.2.0-checksums.sha256` | SHA-256 checksum file for local verification. |

## Local Verification

```bash
python3 -m unittest discover -s tests -v
python3 scripts/build_adapters.py --check --json
python3 scripts/build_release.py --check --json
python3 scripts/check_release_privacy.py --repo-root .
git diff --check
```

After building into `dist/`, verify the local artifacts from inside that
directory:

```bash
shasum -a 256 -c roadmap-delivery-0.2.0-checksums.sha256
```

Optional maintainer host evidence remains separate from the release gate:

```bash
python3 scripts/host_smoke.py --host codex --isolated-home --json
python3 scripts/host_smoke.py --host claude --isolated-home --json
```

Missing host binaries must be reported as `skipped`, not as passed offline
validation.

## Compatibility

- Existing Codex users can continue installing from
  `skill/roadmap-delivery-skill/`.
- Claude users can stage the generated local plugin package from
  `dist/claude/` or the local release artifact.
- The generic markdown pack is a planning artifact, not a supported runtime
  integration for future named hosts.
- Existing helper script paths remain available as wrappers.
- Existing automations without `approval_policy.json` remain conservative.
- Delegated modes require durable approval policy artifacts and readback
  evidence before saved automation retarget, pause, commit, or current-branch
  push operations are treated as pre-approved.

## Limitations

- Release artifacts are local preparation outputs, not a published release.
- Live Codex and Claude checks are optional maintainer smoke checks when those
  host binaries are installed.
- The framework does not control the active model from prompt text; model and
  reasoning changes apply to the next saved run through policy and runner
  readback.
- The GitHub Action companion is offline-first and does not replace host
  runtime smoke checks, security review, compliance review, or marketplace
  acceptance.
- The final deep-review prompt prepares human or fresh-context review, but it
  does not publish, tag, promote, or sync installed packages by itself.

## Publication Boundary

This release candidate can be built, checked, and reviewed locally without
credentials. Publishing a tag, GitHub Release, package registry artifact,
marketplace package, release branch, installed global skill, or live plugin
sync requires explicit human approval.

Commercialisation, pricing, paid support, hosted-service packaging, and
guaranteed response times are not part of this release candidate.
