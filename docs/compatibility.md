# Compatibility

This document records the support boundary for the framework core, generated
Codex skill package, generated Claude plugin package, and future-adapter
planning surface.

## Supported Surfaces

| Surface | Status | Compatibility promise |
|---|---|---|
| `skill/roadmap-delivery-skill/` | Supported | Remains the installable Codex skill package path. |
| Codex helper scripts | Supported | Existing script paths remain executable compatibility wrappers. |
| `python3 -m roadmap_delivery.cli` | Supported | Works from an uninstalled checkout through the repository shim. |
| `roadmap-delivery` console script | Supported after install | Exposed by the local Python package metadata. |
| `automation/<roadmap-slug>/` layout | Supported | State, log, review, alert, and guide files stay repository-local. |
| State schema version 1 | Supported | Current artifacts validate against `schemas/delivery_state.schema.json`. |
| Legacy states without schema version | Compatibility mode | Accepted where legacy behavior is explicitly warning-backed. |
| Model policy file | Supported | `phase_model_policy.json` gates required model and reasoning readback. |
| Approval policy file | Supported | Missing `approval_policy.json` keeps conservative fallback; delegated modes require valid policy readback. |
| Adaptive model policy | Supported | Run quality can retarget the next run within explicit caps and saved automation readback. |
| Completion and stall self-pause | Default safety behavior | Generated policies pause completed automations and pause stalled automations after 2 no-progress runs by default, with opt-out policy flags and readback confirmation. |
| Adapter package generation | Supported | `scripts/build_adapters.py --check` verifies committed Codex and Claude output. |
| Codex package generation | Supported | `scripts/build_codex_package.py --check` remains a compatibility wrapper check. |
| Claude plugin package | Supported local package | Generated under `dist/claude/` with skill, reviewer agent, hooks, and references. |
| Generic markdown pack | Documentation template | Built only as an explicit release artifact for future adapter planning. |
| Local release artifacts | Supported | `scripts/build_release.py --check` verifies reproducible source, Codex, Claude, schema, CLI, and generic bundles. |
| GitHub Action companion | Supported local action | `.github/actions/roadmap-delivery-validate` delegates to the CLI and helper scripts for offline validation. |
| Live host smoke checks | Supported optional evidence | `scripts/host_smoke.py` and `.github/workflows/host-smoke-nightly.yml` provide opt-in Codex and Claude smoke reports with visible skipped results. |
| Nightly host smoke workflow | Opt-in template | The workflow is manual-dispatch by default; remote scheduling requires a separate human-approved repository change. |
| Host capability metadata | Supported | `host-capabilities/codex.yaml` and `host-capabilities/claude.yaml` define the adapter support contract. |

## Host Capability Notes

Codex support is package-based and assumes the Codex runtime supplies skills,
tools, filesystem permissions, model selection, reasoning effort, and
automation scheduling. The framework validates saved automation config when it
is available, but it does not switch the active model from prompt text.

Claude consumes the same `core/`, `schemas/`, and shared library contracts
through a generated plugin package under `dist/claude/`. Offline package
structure checks, adapter parity tests, and demo-roadmap runtime validation are
part of the maintained local support boundary. Live Claude Code loading is an
optional maintainer smoke check when the `claude` binary is available.

Future host adapters should consume the same `core/`, `schemas/`, and shared
library contracts. Any host-specific differences must be represented as
explicit capability metadata, parity tests, smoke checks, and compatibility
notes before a host is listed as supported.

Approval policy, adaptive model policy, and completion or stall pause behavior
are host-neutral control-plane contracts. Hosts that cannot read or update a
saved runner config must expose that limitation as an explicit fallback instead
of claiming automatic retarget or pause support.

GitHub Action validation is a supported local companion surface. Its contract
is offline-first and delegates to the existing CLI, schemas, adapter checks,
and privacy guardrails. Optional live Codex and Claude smoke checks are
maintainer evidence only: missing prerequisites must be reported as skipped,
and successful smoke checks do not replace repository validation or host
capability metadata.

## Marketplace And Distribution Boundary

Marketplace-native package preparation is a local evidence step. Codex and
Claude package checks can prove generated file layout, manifest or frontmatter
metadata, required references, helper script availability, host capability
metadata, documented host parity limits, privacy limits, and human-approved
submission blockers. They do not prove vendor acceptance, live marketplace
availability, installed package synchronization, or external publication.

Human-approved distribution actions include marketplace submission, package
registry upload, branch or tag push, release publication, repository setting
changes, credential use, installed Codex skill synchronization, and installed
Claude plugin synchronization. If one of those operations becomes necessary,
the automation must stop with local evidence recorded rather than performing
the operation automatically.

Host parity limits must remain beside marketplace-preparation guidance:

- Codex support is the generated skill package plus documented local staging,
  helper scripts, validation, and optional live binary smoke checks.
- Claude support is the generated local plugin package plus manifest checks,
  packaged skill/reviewer/hooks, validation, and optional live binary smoke
  checks.
- Optional live-host checks are warnings or evidence notes unless the result is
  recorded; they are not a substitute for repository validators and privacy
  scanning.

## Host Capability Contract

The multi-host adapter work uses explicit capability files instead of burying
host assumptions in prompts:

- `host-capabilities/codex.yaml` records the current Codex baseline.
- `host-capabilities/claude.yaml` records the supported local Claude plugin
  package and host-specific fallback boundaries.
- `host-capabilities/generic.yaml` records the documentation-only generic
  adapter template for future host planning.

The capability files are also the source for host smoke coverage summaries.
Each live smoke section records the offline parity boundary, live status
source, skip visibility rule, opt-in workflow reference, and fallback surface.
The workflow report is evidence for a specific run; the capability file is the
compatibility claim.

Parity levels:

- `required_parity`: behavior must be equivalent across supported hosts.
- `host_specific_enhancement`: behavior may exceed the shared contract on one
  host without becoming required elsewhere.
- `unsupported_by_host`: the host does not expose the capability, so the
  adapter must document the fallback.
- `future_work`: the capability is intentionally outside the current roadmap
  phase.

Claude support is a required-parity target for the core phase-gated workflow,
file-backed state, validation, review artifacts, and release privacy gates. It
uses host-specific fallbacks for recurring automation, model/reasoning
readback, hooks, subagents, and approval UX where Claude Code does not expose
the same surfaces as Codex.

## Claude Hook Safety Boundary

The generated Claude plugin now includes `hooks/hooks.json` plus a small
command helper that reinforces the roadmap delivery contract where Claude Code
plugin hooks support it:

- `PreToolUse` on `Bash` asks for confirmation before destructive git commands,
  broad git staging, publication commands, branch promotion, and package
  upload commands.
- `UserPromptSubmit` injects Blocked Remediation Mode context when a matching
  repository delivery state is blocked.
- `UserPromptSubmit` blocks matching phase-delivery prompts when the delivery
  state is completed, `completed_pending_pause`, or `all_phases_complete`.
- `UserPromptSubmit` injects a privacy/release reminder when the user prompt
  asks for publication, promotion, package, or release work.
- `Stop` blocks a delivered-phase claim that lacks verification evidence and a
  delivered review verdict in the final response.

Unsupported behavior is explicit: these hooks are not a live Claude runtime
smoke test, do not replace repository validators, do not bypass Claude
permissions, do not install or sync any plugin globally, do not provide a
custom MCP server, and do not perform an exhaustive secret scan. Protected
operations still require human approval, and release privacy checks remain the
authoritative gate.

## Human-Approved Operations

The following operations are intentionally outside automatic delivery:

- pushing branches
- merging or promoting to `main`
- publishing release artifacts
- syncing an installed global Codex skill copy
- editing live app automation configuration
- using credentials or external notification sinks
- destructive git operations

Delegated approval modes can pre-approve lower-risk saved automation retarget
and pause operations only when policy, state, and readback agree. They never
pre-approve publication, promotion, unavailable credential use, or destructive
git.

Automation and CLI checks may identify that one of these actions is needed,
but the action itself requires explicit operator approval.
