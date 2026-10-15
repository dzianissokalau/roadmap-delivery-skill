# Installing The Claude Plugin

The Claude adapter is generated into `dist/claude/`. Treat that directory as a
local Claude Code plugin package snapshot. The package includes the roadmap
delivery skill, canonical references, a read-only reviewer agent, and safety
hook reminders.

The generated Claude plugin package is an Apache-2.0 repository artifact. Claude,
Claude Code, and Anthropic names in these instructions describe compatibility
and install targets; they do not imply endorsement, certification, sponsorship,
or official vendor status. See `docs/trademark-and-licensing.md` for the full
boundary.


## Portable Runtime And Python Migration

This package now requires **Python 3.12** (`>=3.12,<3.13`). The previous
Python 3.9+ declaration is retired for installed runtime execution. Python 3.12
provides the TOML parser in its standard library; no pip, tomli, network download,
or globally installed Python library is required by a skill-directory install.
For helpers, use a local Python 3.12 interpreter explicitly when `python3` selects
an older version. For automatic hooks, **`python3.12` must be on the PATH inherited
by Claude Code**. Launch Claude from that environment and verify `python3.12 --version`
there; running a helper with an absolute interpreter does not configure hook PATH.
The hooks use exec-form `python3.12`, never an ambiguous `python3`.
Claude Code **v2.1.295 or later** is required for the configured fail-closed
`onFailure: "block"` behavior on shell-safety and prompt hooks. A missing interpreter,
damaged runtime, or timeout must be repaired before those actions can proceed.
The Stop hook cannot use this launch-failure guarantee; verify its normal JSON
guard separately. See the [Claude hook failure contract](https://code.claude.com/docs/en/hooks#block-the-action-when-a-hook-fails).
These are packaging prerequisites, not a claim of live Claude certification.
Preserve project state and replace the complete staged skill/plugin
package after verification; do not overlay individual runtime or schema files.
Mixed or damaged runtime/resources fail with a reinstall instruction.

The package contains `runtime/roadmap_delivery/`, version metadata, canonical
schemas and a SHA-256 runtime manifest. Helpers resolve those resources relative
to their own installed directory. Claude helpers default to `~/.claude/roadmap-delivery/automations`; an explicit
`AUTONOMOUS_ROADMAP_AUTOMATIONS_DIR` takes precedence. No target-project `schemas/`, source checkout,
`PYTHONPATH`, or site packages are needed. Source-checkout builders remain
development tools; they do not belong on installed import paths.

All helpers are executable from an unrelated project. With `INSTALLED_SKILL`
pointing at the installed skill directory (for Claude, the plugin's
`skills/roadmap-delivery-skill` directory), run:

```bash
python3.12 -I -S "$INSTALLED_SKILL/scripts/inspect_delivery_state.py" --repo-root . --roadmap-slug YOUR_SLUG --json
python3.12 -I -S "$INSTALLED_SKILL/scripts/validate_delivery_artifacts.py" --repo-root . --roadmap-slug YOUR_SLUG --json
python3.12 -I -S "$INSTALLED_SKILL/scripts/compute_progress_signature.py" --repo-root . --roadmap-slug YOUR_SLUG --json
python3.12 -I -S "$INSTALLED_SKILL/scripts/plan_automation_retarget.py" --repo-root . --roadmap-slug YOUR_SLUG --delivered-phase "Phase N - Name" --json
python3.12 -I -S "$INSTALLED_SKILL/scripts/plan_phase_prerequisites.py" --repo-root . --roadmap-slug YOUR_SLUG --json
python3.12 -I -S "$INSTALLED_SKILL/scripts/roadmap_delivery.py" plan-control --repo-root . --roadmap-slug YOUR_SLUG --json
python3.12 -I -S "$INSTALLED_SKILL/scripts/roadmap_delivery.py" scaffold --repo-root . --roadmap-slug NEW_SLUG --dry-run --json
python3.12 -I -S "$INSTALLED_SKILL/scripts/write_operator_alert.py" --repo-root . --roadmap-slug YOUR_SLUG --kind blocked --reason "Local diagnostic" --json
```

Inspection, validation, progress preview, planners and control planning are
read-only. Scaffold defaults to writing; always use `--dry-run` to preview. The alert
command writes a local alert. `compute_progress_signature.py --record-run --run-id ID` uses shared semantic
accounting; a preview signature is diagnostic, never progress evidence.

The separately installed CLI uses the same bundled schemas and stdlib runtime.
Extract the local CLI source archive, then build/install offline in an isolated
Python 3.12 virtual environment. BUILD_PYTHON must already have pip>=22.3,
setuptools>=68 and wheel available locally:

```bash
export CLI_TRIAL="$(mktemp -d)"
export CLI_ENV="$CLI_TRIAL/venv"
export BUILD_PYTHON=/path/to/python3.12-with-local-build-tools
"$BUILD_PYTHON" -m venv --without-pip "$CLI_ENV"
"$BUILD_PYTHON" -m pip wheel --no-index --no-deps --no-build-isolation \
  --wheel-dir "$CLI_TRIAL/wheels" /path/to/extracted-cli-source
"$BUILD_PYTHON" -m pip --python "$CLI_ENV/bin/python" install --no-index --no-deps \
  "$CLI_TRIAL"/wheels/roadmap_delivery-*.whl
"$CLI_ENV/bin/roadmap-delivery" validate --repo-root /path/to/project --roadmap-slug YOUR_SLUG --json
```

The build backend is an explicit build-time prerequisite, not a hidden runtime
dependency. If absent, provision it separately before installation; fixtures
never download it. The supported Python 3.12 runtime is tested with site packages
disabled for skill/release installs and a fresh venv for local CLI installation.
Other Python versions are outside the current verified portable support range.

## Short Path

Build the local release artifacts, extract the Claude plugin package into a
temporary plugin directory, and run the offline validation commands before
touching an active plugin directory:

```bash
export SMOKE_HOME="$(mktemp -d)"
python3 scripts/build_release.py --output-dir dist --json
mkdir -p "$SMOKE_HOME/claude/plugins/roadmap-delivery"
tar -xzf dist/roadmap-delivery-claude-plugin-0.3.0.tar.gz \
  -C "$SMOKE_HOME/claude/plugins/roadmap-delivery" \
  --strip-components=1
```

## Verification Path

From the repository root:

```bash
python3 scripts/build_adapters.py --adapter claude --check
python3 scripts/build_release.py --check --json
python3 scripts/check_release_privacy.py --repo-root .
python3 -m unittest tests.test_install_smoke -v
python3 -m json.tool dist/claude/.claude-plugin/plugin.json >/dev/null
```

## Marketplace Readiness Checklist

Use this checklist when evaluating whether the Claude plugin package is ready
for a human-approved marketplace, registry, or public distribution submission.
The automation may prepare this evidence locally, but it must not submit,
publish, sync an installed plugin, or use credentials.

| Area | Claude package evidence |
|---|---|
| Required metadata | `dist/claude/.claude-plugin/plugin.json` declares plugin identity, version `0.3.0`, author, description, and Apache-2.0 license; release notes and the release manifest record checksums and package identity. |
| Package contents | `.claude-plugin/plugin.json`, `README.md`, `skills/roadmap-delivery-skill/`, `agents/reviewer.md`, and `hooks/` are generated from adapter metadata and checked by `python3 scripts/build_adapters.py --adapter claude --check`. |
| Compatibility limits | Support is limited to the generated local Claude Code plugin package, file-backed validators, repository-local review artifacts, safety hook reminders, and optional live `claude --help` smoke coverage. |
| Privacy limits | Release-bound packages must exclude `automation/`, `roadmaps/`, `.git/`, `.codex/`, local alerts, review transcripts, private paths, and credentials; run `python3 scripts/check_release_privacy.py --repo-root .`. |
| Submission blockers | Marketplace submission, package registry upload, branch or tag pushes, repository setting changes, installed-plugin synchronization, and credential use require explicit human approval. |

The native Claude path for this repository is the generated local plugin
package. Manual fallback is direct staging into an isolated `CLAUDE_PLUGIN_DIR`
after the checks above pass.

## Stage An Isolated Plugin

This stages the plugin in a temporary plugin directory and leaves any active
Claude Code plugin directory untouched.

```bash
export SMOKE_HOME="$(mktemp -d)"
mkdir -p "$SMOKE_HOME/claude/plugins"
cp -R dist/claude "$SMOKE_HOME/claude/plugins/roadmap-delivery"
```

To stage from the local release artifact instead, build artifacts into `dist/`
and extract the Claude plugin package into the same isolated plugin directory:

```bash
python3 scripts/build_release.py --output-dir dist --json
mkdir -p "$SMOKE_HOME/claude/plugins/roadmap-delivery"
tar -xzf dist/roadmap-delivery-claude-plugin-0.3.0.tar.gz \
  -C "$SMOKE_HOME/claude/plugins/roadmap-delivery" \
  --strip-components=1
```

If the `claude` binary is installed, this optional host check should return
usage text:

```bash
CLAUDE_PLUGIN_DIR="$SMOKE_HOME/claude/plugins" claude --help
```

If `claude` is not installed, skip only the host binary check. The plugin
structure and file-backed runtime checks still run offline.

The supported behavior is limited to the generated local plugin package,
repository validators, documented staging flow, and offline smoke coverage.
Optional live binary checks do not prove full host feature parity.

## Run The Optional Smoke Harness

Use the local smoke harness when you want one command that validates the Claude
plugin package without touching an active Claude configuration:

```bash
python3 scripts/host_smoke.py --host claude --isolated-home --json
```

The harness stages `dist/claude/` under a temporary `CLAUDE_PLUGIN_DIR`, runs
file-backed demo roadmap validation with temporary automation readback,
verifies the generated hook guard asks before destructive git commands, and
then runs `claude --help` only when the binary is available. Missing `claude`
is reported as `skipped`; it is not treated as a passed live check.

Hook checks are conservative guardrails and reminders. They are not complete
DLP, host permission enforcement, marketplace certification, or proof of full
Claude feature parity.

## Prepare Demo Automation Readback

Copy the demo fixture into a temporary git checkout, then copy its committed
sample automation config into the temporary Codex-style automation readback
directory used by the local validators:

```bash
export SMOKE_REPO="$SMOKE_HOME/demo-roadmap"
cp -R examples/demo-roadmap "$SMOKE_REPO"
git -C "$SMOKE_REPO" init -b codex/demo-roadmap-phase-1
git -C "$SMOKE_REPO" add .
git -C "$SMOKE_REPO" \
  -c user.name=Demo \
  -c user.email=demo.invalid \
  commit -m "demo fixture"

mkdir -p "$SMOKE_HOME/.codex/automations/demo-roadmap-delivery"
python3 - <<'PY'
from pathlib import Path
import os

repo = Path(os.environ["SMOKE_REPO"]).resolve()
home = Path(os.environ["SMOKE_HOME"])
source = repo / "automation-config" / "demo-roadmap-delivery" / "automation.toml"
target = home / ".codex" / "automations" / "demo-roadmap-delivery" / "automation.toml"
text = source.read_text(encoding="utf-8")
text = text.replace('cwds = ["."]', f'cwds = ["{repo}"]')
target.write_text(text, encoding="utf-8")
PY
```

## Validate The Demo Roadmap

Run the same file-backed runtime commands the Claude skill asks a maintainer to
use before claiming delivery:

```bash
AUTONOMOUS_ROADMAP_AUTOMATIONS_DIR="$SMOKE_HOME/.codex/automations" \
python3.12 -I -S "$SMOKE_HOME/claude/plugins/roadmap-delivery/skills/roadmap-delivery-skill/scripts/roadmap_delivery.py" inspect \
  --repo-root "$SMOKE_REPO" \
  --roadmap-slug demo-roadmap \
  --automation-id demo-roadmap-delivery \
  --strict \
  --json

AUTONOMOUS_ROADMAP_AUTOMATIONS_DIR="$SMOKE_HOME/.codex/automations" \
python3.12 -I -S "$SMOKE_HOME/claude/plugins/roadmap-delivery/skills/roadmap-delivery-skill/scripts/roadmap_delivery.py" validate \
  --repo-root "$SMOKE_REPO" \
  --roadmap-slug demo-roadmap \
  --automation-id demo-roadmap-delivery \
  --strict \
  --json
```

For blocked-remediation and model-policy-mismatch fixtures, follow
`examples/demo-roadmap/runtime-checklist.md` in a temporary copy of the fixture.

## Rollback Or Cleanup

Remove the temporary smoke home when validation is complete:

```bash
rm -rf "$SMOKE_HOME"
```

If you later choose to update an active Claude plugin directory, keep a backup
of the previous `roadmap-delivery` plugin directory. Roll back by restoring that
backup or by removing only the staged `roadmap-delivery` plugin; do not delete
unrelated local plugins.

## Updating An Active Plugin

Only update a live Claude Code plugin directory after adapter checks, release
checks, privacy scanning, and demo validation pass. Installed-plugin
synchronization is a human-approved operation; keep a backup of the previous
plugin directory and do not overwrite unrelated local plugins.
