# Host Smoke Checks

This guide defines the safety contract for offline validation and optional live
host smoke checks. The Codex and Claude smoke harnesses are available as
explicit local script modes; normal repository validation remains offline.

## Default Mode

Repository validation is offline by default. The default path must run without
network access, repository secrets, global host installation, or a saved Codex
or Claude runner.

Offline validation may run:

- `python3 -m roadmap_delivery.cli validate`
- schema validation tests
- adapter parity checks
- release privacy checks
- `git diff --check`

Offline validation must not pretend to run a live Codex or Claude host. If a
future workflow includes live checks, their result must be reported separately
from offline validation.

## Live Check Boundary

Live host smoke checks are optional maintainer evidence. They can show that a
small supported path still loads or executes in a particular host runner, but
they cannot prove compliance, safety, marketplace readiness, or full host
parity.

Live checks must be explicitly enabled by an operator or workflow input. When
enabled, they must:

- print the selected host, mode, and prerequisites checked
- report missing prerequisites as `skipped`, not `passed`
- fail the live-check step when an enabled live check starts and then fails
- keep offline validation status separate from live host status
- avoid printing secrets, private paths, local automation logs, or transcripts
- avoid repository settings changes, secret creation, publication, promotion,
  installed package synchronization, or destructive git operations

## Codex Prerequisites

A Codex live smoke check may run only when all required prerequisites are
available to the runner:

- a Codex execution surface or binary that can run the generated skill package
- a checkout containing `skill/roadmap-delivery-skill/`
- an explicit test roadmap, state directory, and temporary or approved
  automation config
- model and reasoning readback when the smoke path exercises phase delivery
- approval policy that allows the specific local operation being tested

If a Codex binary, saved automation config, model readback, or required
filesystem permission is unavailable, the check must be marked `skipped` with a
reason. A skipped Codex live check is not a failed offline validation run and is
not evidence that Codex runtime behavior passed.

## Codex Smoke Harness

Run the optional Codex harness only when a maintainer explicitly wants live host
evidence:

```bash
python3 scripts/host_smoke.py --host codex --isolated-home --json
```

The harness always stages `skill/roadmap-delivery-skill/` and the demo roadmap
under a temporary `CODEX_HOME`. It then runs the installed helper scripts
against the demo fixture. When a `codex` binary is available, it runs
`codex --help` with that temporary home; when the binary is missing, the live
binary check is reported as `skipped`.

The JSON report separates `offline_status` from `live_status`. A missing Codex
binary produces top-level `status: "skipped"` with offline package checks still
reported as passed. A live binary failure produces `status: "failed"`.

## Claude Prerequisites

A Claude live smoke check may run only when all required prerequisites are
available to the runner:

- a Claude Code execution surface or binary that can load the local plugin
  package
- a checkout containing `dist/claude/`
- a temporary or operator-approved plugin loading path
- a test roadmap and repository-local state directory
- approval policy that allows the specific local operation being tested

Claude recurring automation is not assumed by this project. If a live Claude
check cannot prove plugin loading or required permissions, the result must be
`skipped` with a reason. Installing or syncing a global Claude plugin remains a
human-approved operation.

## Claude Smoke Harness

Run the optional Claude harness only when a maintainer explicitly wants local
Claude package evidence:

```bash
python3 scripts/host_smoke.py --host claude --isolated-home --json
```

The harness validates the generated `dist/claude/` package layout, parses the
plugin manifest, stages the plugin under a temporary `CLAUDE_PLUGIN_DIR`, runs
file-backed demo roadmap validation with temporary automation readback, and
verifies that the generated hook guard asks before destructive git commands.
It does not install or sync an active Claude plugin.

When a `claude` binary is available, the harness runs `claude --help` with the
temporary plugin directory. When the binary is missing, the live binary check is
reported as `skipped` while the offline package checks can still pass. Hook
checks are guardrails and reminders; they are not complete DLP, permission
enforcement, or marketplace certification.

## Result Semantics

Use separate status values for each validation surface:

| Surface | Missing prerequisite | Runtime failure | Successful run |
|---|---|---|---|
| Offline validation | `failed` when required files are missing | `failed` | `passed` |
| Codex live smoke | `skipped` | `failed` | `passed` |
| Claude live smoke | `skipped` | `failed` | `passed` |

Workflow summaries and reports should include counts for passed, failed,
warning, and skipped checks. A skipped live check must remain visible in logs,
reports, and action outputs.

## Opt-In Workflow Template

The repository includes `.github/workflows/host-smoke-nightly.yml` as an
opt-in maintainer workflow template. It is dispatch-only by default so adding
the file does not enable a remote schedule. A maintainer who wants recurring
nightly evidence can enable or schedule it only through a separate
human-approved repository workflow change.

The workflow accepts explicit `run_codex` and `run_claude` inputs. When a host
is selected, it runs the matching smoke harness with `--isolated-home`, writes
the raw host report under `host-smoke-reports/`, and uploads those reports as
an artifact. Missing host binaries are recorded as `skipped` in the host
report; they are not folded into offline validation success.

The workflow also writes `host-smoke-reports/host-coverage.json` from host
capability metadata. That summary records each host's live smoke support
status, offline parity boundary, skipped live checks, and fallback surface.
Capability metadata remains the source for compatibility claims; workflow
logs are evidence for a specific run only.

The current Codex and Claude smoke modes do not require repository secrets.
If a maintainer later adds authenticated host setup, secret creation and
schedule activation remain manual repository operations outside automation.

## False-Safety Limits

CI and live host smoke checks cannot prove:

- vendor service availability
- marketplace acceptance
- legal, security, or compliance approval
- model quality or deterministic future behavior
- full equivalence across Codex, Claude, and future hosts
- that local operator policies are appropriate for another repository
- that unpublished release artifacts are safe to publish

The authoritative support boundary remains the repository source, schemas,
host capability metadata, approval policy, validation output, and review
evidence.
