# Installing The Codex Package

The Codex adapter is generated into `skill/roadmap-delivery-skill/`. Treat that
directory as the installable package snapshot; do not sync it into a live Codex
home until the generated package and smoke checks pass.

The generated Codex package is an Apache-2.0 repository artifact. Codex and
OpenAI names in these instructions describe compatibility and install targets;
they do not imply endorsement, certification, sponsorship, or official vendor
status. See `docs/trademark-and-licensing.md` for the full boundary.


## Portable Runtime And Python Migration

This package now requires **Python 3.12** (`>=3.12,<3.13`). The previous
Python 3.9+ declaration is retired for installed runtime execution. Python 3.12
provides the TOML parser in its standard library; no pip, tomli, network download,
or globally installed Python library is required by a skill-directory install.
Use a local Python 3.12 interpreter explicitly when `python3` selects an older
version. Preserve project state and replace the complete staged skill/plugin
package after verification; do not overlay individual runtime or schema files.
Mixed or damaged runtime/resources fail with a reinstall instruction.

The package contains `runtime/roadmap_delivery/`, version metadata, canonical
schemas and a SHA-256 runtime manifest. Helpers resolve those resources relative
to their own installed directory. No target-project `schemas/`, source checkout,
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

Build the local release artifacts, extract the Codex package into a temporary
Codex home, and run the offline validation commands before touching an active
install:

```bash
export SMOKE_HOME="$(mktemp -d)"
python3 scripts/build_release.py --output-dir dist --json
mkdir -p "$SMOKE_HOME/.codex/skills/roadmap-delivery-skill"
tar -xzf dist/roadmap-delivery-codex-skill-0.3.0.tar.gz \
  -C "$SMOKE_HOME/.codex/skills/roadmap-delivery-skill" \
  --strip-components=1
```

## Verification Path

From the repository root:

```bash
python3 scripts/build_adapters.py --adapter codex --check
python3 scripts/build_release.py --check --json
python3 scripts/check_release_privacy.py --repo-root .
python3 -m unittest tests.test_install_smoke -v
```

Optional live-host smoke, only when a maintainer explicitly wants Codex runtime
evidence:

```bash
python3 scripts/host_smoke.py --host codex --isolated-home --json
```

This command uses a temporary `CODEX_HOME`, validates the demo roadmap through
the staged helper scripts, and reports a missing `codex` binary as `skipped`.
It must not be used as a package sync step for the active Codex home.

## Marketplace Readiness Checklist

Use this checklist when evaluating whether the Codex package is ready for a
human-approved marketplace, registry, or public distribution submission. The
automation may prepare this evidence locally, but it must not submit, publish,
sync an installed skill, or use credentials.

| Area | Codex package evidence |
|---|---|
| Required metadata | `skill/roadmap-delivery-skill/SKILL.md` declares the skill name and description; release notes and the release manifest record version `0.3.0`, Apache-2.0 licensing, checksums, and package identity. |
| Package contents | `SKILL.md`, `agents/openai.yaml`, canonical `references/`, and helper `scripts/` are generated from adapter metadata and checked by `python3 scripts/build_adapters.py --adapter codex --check`. |
| Compatibility limits | Support is limited to file-backed roadmap artifacts, local helper scripts, saved automation readback when available, and documented Codex runner behavior. Optional live `codex --help` does not prove full host feature parity. |
| Privacy limits | Release-bound packages must exclude `automation/`, `roadmaps/`, `.git/`, `.codex/`, local alerts, review transcripts, private paths, and credentials; run `python3 scripts/check_release_privacy.py --repo-root .`. |
| Submission blockers | Marketplace submission, package registry upload, branch or tag pushes, repository setting changes, installed-skill synchronization, and credential use require explicit human approval. |

The native Codex path for this repository is the generated skill package.
Manual fallback is direct staging into an isolated `${CODEX_HOME}` or a
temporary `.codex/skills/roadmap-delivery-skill` directory after the checks
above pass.

## Stage An Isolated Install

This stages the package in a temporary Codex home and leaves the active Codex
installation untouched.

```bash
export SMOKE_HOME="$(mktemp -d)"
mkdir -p "$SMOKE_HOME/.codex/skills"
cp -R skill/roadmap-delivery-skill \
  "$SMOKE_HOME/.codex/skills/roadmap-delivery-skill"
```

To stage from the local release artifact instead, build artifacts into `dist/`
and extract the Codex package into the same isolated package directory:

```bash
python3 scripts/build_release.py --output-dir dist --json
mkdir -p "$SMOKE_HOME/.codex/skills/roadmap-delivery-skill"
tar -xzf dist/roadmap-delivery-codex-skill-0.3.0.tar.gz \
  -C "$SMOKE_HOME/.codex/skills/roadmap-delivery-skill" \
  --strip-components=1
```

If the `codex` binary is installed, this optional host check should return
usage text without touching the active Codex home:

```bash
CODEX_HOME="$SMOKE_HOME/.codex" codex --help
```

If `codex` is not installed, skip only the host binary check. The package
layout and helper-script smoke checks still run offline.

The supported behavior is limited to the generated package layout, helper
scripts, documented install flow, and file-backed validation. Optional live
binary checks do not prove full host feature parity.

The scripted form is:

```bash
python3 scripts/host_smoke.py --host codex --isolated-home --json
```

It reports separate offline and live statuses so a skipped binary check cannot
be mistaken for a successful live Codex run.

## Prepare Demo Automation Readback

Copy the demo fixture into a temporary git checkout, then copy its committed
sample automation config into the temporary home and rewrite the checkout path
for this machine:

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

Run the installed helper scripts against the demo roadmap:

```bash
AUTONOMOUS_ROADMAP_AUTOMATIONS_DIR="$SMOKE_HOME/.codex/automations" \
python3.12 -I -S "$SMOKE_HOME/.codex/skills/roadmap-delivery-skill/scripts/inspect_delivery_state.py" \
  --repo-root "$SMOKE_REPO" \
  --roadmap-slug demo-roadmap \
  --automation-id demo-roadmap-delivery \
  --json

AUTONOMOUS_ROADMAP_AUTOMATIONS_DIR="$SMOKE_HOME/.codex/automations" \
python3.12 -I -S "$SMOKE_HOME/.codex/skills/roadmap-delivery-skill/scripts/validate_delivery_artifacts.py" \
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

If you later choose to update an active Codex home, keep a backup of the
previous `roadmap-delivery-skill` directory. Roll back by restoring that backup
or by removing only the staged `roadmap-delivery-skill` directory; do not delete
unrelated local skills.

## Updating An Active Install

Only update a live Codex home after adapter checks, release checks, privacy
scanning, and demo validation pass. Installed-skill synchronization is a
human-approved operation; keep a backup of the previous
`roadmap-delivery-skill` directory and do not overwrite unrelated local skills.
