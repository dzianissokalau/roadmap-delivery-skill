# Architecture

Roadmap Delivery Skill is a file-backed delivery framework. The durable control
plane is made of roadmap files, delivery state, append-only logs, review
artifacts, alert files, git branches, and verification output.

## Source Layout

| Area | Path | Role |
|---|---|---|
| Workflow core | `core/references/` | Host-neutral rules for setup, delivery, review/fix loops, state handling, finalization, troubleshooting, and model policy. |
| Reusable text | `core/templates/`, `core/prompts/` | Artifact templates and guard text used by setup and automation prompts. |
| Data contracts | `schemas/` | JSON schemas for delivery state, model policy, review artifacts, and automation run logs. |
| Shared code | `src/roadmap_delivery/` | Python library for validation, inspection, semantic run accounting, TOML parsing, git helpers, policy gates, and CLI commands. |
| CLI shim | `roadmap_delivery/__init__.py` | Checkout-local module shim so `python3 -m roadmap_delivery.cli` works before install. |
| Codex adapter | `adapters/codex/` | Manifest and templates that render the installable Codex skill package. |
| Codex package | `skill/roadmap-delivery-skill/` | Committed generated package and compatibility script paths. |
| Demo | `examples/demo-roadmap/` | Offline fixture for scaffold, inspect, validate, blocked-run, and model-policy smoke tests. |
| Automation state | `automation/<roadmap-slug>/` | Local state, logs, alerts, reviews, and automation guides for a roadmap run. |

## Delivery Flow

1. The roadmap names the current phase and owned files.
2. `delivery_state.json` records the selected phase, model requirements,
   verification summary, review summary, and completion flags.
3. The saved automation config is read back before implementation so model and
   reasoning requirements can be enforced.
4. Work happens on `codex/<roadmap-slug>-phase-<n>`.
5. Required verification runs after implementation.
6. A review artifact records findings, residual risk, and a final verdict.
7. State and log advance only after the phase gate is delivered.

Blocked state is a remediation mode. The next run classifies the blocker before
retrying delivery and only repairs local or already-authorized automation
configuration issues.

## Adapter Boundary

Canonical behavior belongs in `core/`, `schemas/`, and `src/roadmap_delivery/`.
Host-specific packaging belongs in `adapters/<host>/`. The Codex adapter
renders `skill/roadmap-delivery-skill/` and snapshot tests catch generated
package drift.

Codex and Claude packages contain a self-contained standard-library runtime.
Planners and compatibility helpers import canonical decisions; no generated
controller copies remain. The generic markdown pack is documentation only.
New host adapters should be added without forking
the workflow rules. Host-specific capability gaps should be explicit in adapter
metadata and compatibility docs.

## Release Boundary

`scripts/build_release.py` creates deterministic local artifacts from the current
filesystem, including uncommitted source changes. Record both git HEAD and
source hashes outside the archives; HEAD alone does not identify a candidate. Release bundles include framework sources, the generated Codex
package, the generated Claude plugin package, schema and CLI bundles, and the
documentation-only generic markdown pack. They exclude roadmap automation
state, review files, local alerts, `.git/`, and `.codex/`.

Publication to GitHub Releases, package indexes, Homebrew, npm, or other
external channels is not automated by this repository. It requires explicit
human approval after local verification passes.

## Runtime Entrypoints

`control.decide_control` owns ordered terminal, activation, remediation and phase
decisions. `approval` resolves named/context authority, `policy` constrains model
targets, `progress` validates and journals unique semantic outcomes, and
`automation` resumes receipt-backed host effects. `reports` loads evidence for
inspection, prerequisite and retarget planners; CLI and installed helpers call
these same functions. Scaffold/wizard proposals expose the missing readback
plan without claiming a configured runner. Host hooks add context from the same
controller while allowing terminal closeout to proceed. A file read supplies
observed settings, never live host capabilities. Saved prompt migration remains
an explicit scoped upgrade; global skill synchronization does not migrate it.
