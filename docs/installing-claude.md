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

## Short Path

Build the local release artifacts, extract the Claude plugin package into a
temporary plugin directory, and run the offline validation commands before
touching an active plugin directory:

```bash
export SMOKE_HOME="$(mktemp -d)"
python3 scripts/build_release.py --output-dir dist --json
mkdir -p "$SMOKE_HOME/claude/plugins/roadmap-delivery"
tar -xzf dist/roadmap-delivery-claude-plugin-0.2.0.tar.gz \
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
| Required metadata | `dist/claude/.claude-plugin/plugin.json` declares plugin identity, version `0.2.0`, author, description, and Apache-2.0 license; release notes and the release manifest record checksums and package identity. |
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
tar -xzf dist/roadmap-delivery-claude-plugin-0.2.0.tar.gz \
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
PYTHONPATH="$PWD/src" \
python3 -m roadmap_delivery.cli inspect \
  --repo-root "$SMOKE_REPO" \
  --roadmap-slug demo-roadmap \
  --automation-id demo-roadmap-delivery \
  --strict \
  --json

AUTONOMOUS_ROADMAP_AUTOMATIONS_DIR="$SMOKE_HOME/.codex/automations" \
PYTHONPATH="$PWD/src" \
python3 -m roadmap_delivery.cli validate \
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
