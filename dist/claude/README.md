# Roadmap Delivery Claude Adapter

This is a generated local Claude Code plugin package for Roadmap Delivery Skill.
It is an Apache-2.0 repository artifact. Claude, Claude Code, and Anthropic names
are compatibility labels only and do not imply endorsement, certification,
sponsorship, or official vendor status.

It includes the main roadmap delivery skill, canonical workflow references,
a read-only reviewer agent pattern for phase-gated review, and conservative
Claude hook guards for roadmap delivery safety reminders. It also includes
provider-neutral model-role guidance that records when a host cannot prove or
set a reasoning-effort value.

Approval policy, adaptive model policy, and completion/stall self-pause rules
come from the same core workflow sources used by the Codex package. Claude
adapters must preserve conservative fallbacks: unsupported recurring
automation, model/reasoning readback, or status-only pause surfaces fall back to
repository validation, local alerts, and explicit operator action rather than
claiming host support.

Support is limited to the generated local plugin package, repository validators,
documented staging flow, offline package checks, and optional live smoke checks
when a maintainer has the `claude` binary available. Do not claim full host
feature parity beyond those validated surfaces.

## Local Checks

1. Regenerate the package from the repository root:
   `python3 scripts/build_adapters.py --adapter claude --write`
2. Check committed output:
   `python3 scripts/build_adapters.py --adapter claude --check`
3. Build local release artifacts:
   `python3 scripts/build_release.py --check`

The package is verified by offline structure checks and local demo-roadmap
runtime validation. Live Claude Code loading remains an optional maintainer
smoke check when the `claude` binary is available; publication or installed
plugin synchronization still requires explicit human approval.

## Marketplace Readiness Checklist

- Required metadata: `.claude-plugin/plugin.json` declares package identity,
  version, author, description, and Apache-2.0 license; release notes and the
  release manifest record checksums and package identity.
- Package contents: the plugin manifest, README, packaged skill, read-only
  reviewer agent, safety hooks, and canonical references are generated from
  adapter metadata.
- Compatibility limits: support is limited to local plugin staging,
  repository validators, file-backed review artifacts, safety reminders, and
  optional live `claude --help` smoke coverage.
- Host capability metadata: `host-capabilities/claude.yaml` records supported,
  unsupported, fallback, and protected-operation boundaries for this package.
- Privacy limits: release-bound packages must exclude automation state,
  roadmaps, local alerts, review transcripts, private paths, and credentials.
- Submission blockers: marketplace submission, package registry upload,
  installed-plugin synchronization, branch or tag pushes, repository setting
  changes, and credential use require explicit human approval.
