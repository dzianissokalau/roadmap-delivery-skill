# Adapters

Roadmap Delivery uses adapters to package the same host-neutral workflow for
different AI coding hosts. Canonical behavior stays in `core/`, `schemas/`, and
`src/roadmap_delivery/`; adapter directories only describe how a host receives
that workflow.

Adapter and host names are descriptive compatibility labels. Generated package
snapshots are Apache-2.0 repository artifacts unless a file says otherwise, and
no adapter README, manifest, or release note should imply vendor endorsement,
certification, sponsorship, or official status. See
`docs/trademark-and-licensing.md`.

## Current Adapter Set

| Adapter | Status | Default build | Purpose |
|---|---|---:|---|
| `codex` | Supported package | Yes | Generated Codex skill package. |
| `claude` | Supported local plugin package | Yes | Generated Claude plugin package. |
| `generic` | Documentation template | No | Markdown and schema pack for future adapter planning. |

The generic adapter is intentionally not a support claim for Continue, Cline,
Roo Code, OpenHands, or any other named host. Those hosts need separate
capability files, package metadata, tests, smoke checks, and compatibility notes
before they can be listed as supported.

## Generic Pack

Generate the generic documentation pack into a temporary output directory:

```bash
python3 scripts/build_adapters.py --adapter generic --write --output-root /tmp/roadmap-adapter-pack
```

Check that the generic adapter still renders:

```bash
python3 scripts/build_adapters.py --adapter generic --check
```

The default adapter build remains limited to concrete package outputs:

```bash
python3 scripts/build_adapters.py --check
```

## Adding A Host Adapter

Use this minimum path for a new host:

1. Create `host-capabilities/<host>.yaml` with support status, parity levels,
   fallbacks, model readback behavior, filesystem expectations, and protected
   operations.
2. Add `adapters/<host>/package.py` that renders deterministic output from
   core references, schemas, and host-specific templates.
3. Keep unsupported host features explicit in the capability file and generated
   README.
4. Add focused adapter tests for render checks, output-root regeneration,
   snapshot or manifest drift, host capability metadata, and support-claim
   wording.
5. Add install or runtime smoke checks that can pass without credentials or
   global host mutation.
6. Update compatibility and release documentation only after the checks prove
   the support boundary.

Do not add a host to the default build until its package is meant to be treated
as a concrete maintained adapter.

## Marketplace Preparation

Marketplace preparation means collecting enough local package evidence for a
human to decide whether to submit a package. It is not publication approval,
host endorsement, installed package synchronization, or a claim that a live
host marketplace has accepted the project.

| Adapter | Required metadata | Package contents | Compatibility and privacy limits | Submission blockers |
|---|---|---|---|---|
| Codex | Skill frontmatter in `skill/roadmap-delivery-skill/SKILL.md`, release notes, release manifest, Apache-2.0 license, and checksums. | `SKILL.md`, `agents/openai.yaml`, canonical references, and helper scripts generated from `adapters/codex/package_manifest.json`. | File-backed roadmap state, local validators, saved automation readback when available, privacy scan, and optional live Codex binary smoke only. | Marketplace submission, package registry upload, branch or tag push, installed-skill sync, credentials, and repository setting changes. |
| Claude | `.claude-plugin/plugin.json`, generated README, release notes, release manifest, Apache-2.0 license, and checksums. | Plugin manifest, README, packaged skill, read-only reviewer agent, safety hooks, and canonical references generated from `adapters/claude/package.py`. | Local Claude Code plugin package, repository validators, safety reminders, privacy scan, and optional live Claude binary smoke only. | Marketplace submission, package registry upload, branch or tag push, installed-plugin sync, credentials, and repository setting changes. |
| Generic | Generic pack metadata in the release manifest when built explicitly. | Documentation and schema planning bundle only. | Future-host planning; no runtime support or named host parity claim. | Any named-host support claim before capability metadata, tests, docs, and smoke checks exist. |

`scripts/build_adapters.py --check --json` reports marketplace-readiness
checks for the supported Codex and Claude package outputs. Those checks cover
required generated files, host capability metadata, install documentation,
compatibility limits, privacy limits, and submission blockers. A readiness
check failure is an adapter check failure, not an instruction to publish.
