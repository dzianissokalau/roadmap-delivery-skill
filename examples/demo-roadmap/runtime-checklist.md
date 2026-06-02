# Demo Roadmap Runtime Checklist

Use this checklist from the repository root. It creates temporary state, stages
the generated packages, and exercises the demo roadmap without credentials,
publication, or changes to a live Codex or Claude install.

## 1. Create A Temporary Demo Checkout

```bash
export SMOKE_HOME="$(mktemp -d)"
export SMOKE_REPO="$SMOKE_HOME/demo-roadmap"
cp -R examples/demo-roadmap "$SMOKE_REPO"
git -C "$SMOKE_REPO" init -b codex/demo-roadmap-phase-1
git -C "$SMOKE_REPO" add .
git -C "$SMOKE_REPO" \
  -c user.name=Demo \
  -c user.email=demo.invalid \
  commit -m "demo fixture"
```

## 2. Install Generated Package Snapshots

Stage the Codex package:

```bash
mkdir -p "$SMOKE_HOME/.codex/skills"
cp -R skill/roadmap-delivery-skill \
  "$SMOKE_HOME/.codex/skills/roadmap-delivery-skill"
```

Stage the Claude plugin:

```bash
mkdir -p "$SMOKE_HOME/claude/plugins"
cp -R dist/claude "$SMOKE_HOME/claude/plugins/roadmap-delivery"
```

## 3. Prepare Automation Readback

```bash
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

## 4. Inspect And Validate The Demo Roadmap

Codex helper-script path:

```bash
AUTONOMOUS_ROADMAP_AUTOMATIONS_DIR="$SMOKE_HOME/.codex/automations" \
PYTHONPATH="$PWD/src" \
"$SMOKE_HOME/.codex/skills/roadmap-delivery-skill/scripts/inspect_delivery_state.py" \
  --repo-root "$SMOKE_REPO" \
  --roadmap-slug demo-roadmap \
  --automation-id demo-roadmap-delivery \
  --json

AUTONOMOUS_ROADMAP_AUTOMATIONS_DIR="$SMOKE_HOME/.codex/automations" \
PYTHONPATH="$PWD/src" \
"$SMOKE_HOME/.codex/skills/roadmap-delivery-skill/scripts/validate_delivery_artifacts.py" \
  --repo-root "$SMOKE_REPO" \
  --roadmap-slug demo-roadmap \
  --automation-id demo-roadmap-delivery \
  --strict \
  --json
```

Claude plugin runtime path:

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

## 5. Trigger The Blocked-Remediation Fixture

```bash
cp examples/demo-roadmap/scenarios/blocked-remediation/delivery_state.json \
  "$SMOKE_REPO/automation/demo_roadmap/delivery_state.json"
cp examples/demo-roadmap/scenarios/blocked-remediation/review_fix_state.json \
  "$SMOKE_REPO/automation/demo_roadmap/review_fix_state.json"
cp examples/demo-roadmap/scenarios/blocked-remediation/demo-roadmap-phase-1-review-iteration-1.md \
  "$SMOKE_REPO/automation/demo_roadmap/reviews/demo-roadmap-phase-1-review-iteration-1.md"

AUTONOMOUS_ROADMAP_AUTOMATIONS_DIR="$SMOKE_HOME/.codex/automations" \
PYTHONPATH="$PWD/src" \
python3 -m roadmap_delivery.cli inspect \
  --repo-root "$SMOKE_REPO" \
  --roadmap-slug demo-roadmap \
  --automation-id demo-roadmap-delivery \
  --json
```

The inspect output should show `blocked_remediation_required: true`.

## 6. Trigger The Delegated-Local Policy Fixture

```bash
cp examples/demo-roadmap/scenarios/delegated-local/approval_policy.json \
  "$SMOKE_REPO/automation/demo_roadmap/approval_policy.json"

AUTONOMOUS_ROADMAP_AUTOMATIONS_DIR="$SMOKE_HOME/.codex/automations" \
PYTHONPATH="$PWD/src" \
python3 -m roadmap_delivery.cli inspect \
  --repo-root "$SMOKE_REPO" \
  --roadmap-slug demo-roadmap \
  --automation-id demo-roadmap-delivery \
  --json
```

The inspect output should show `autonomy_mode: delegated_local`,
`pause_saved_automation` as allowed, and `push_current_phase_branch` as
ask-first.

## 7. Trigger The Model-Policy-Mismatch Fixture

```bash
python3 - <<'PY'
from pathlib import Path
import os

repo = Path(os.environ["SMOKE_REPO"]).resolve()
home = Path(os.environ["SMOKE_HOME"])
source = Path("examples/demo-roadmap/scenarios/model-policy-mismatch/automation.toml")
target = home / ".codex" / "automations" / "demo-roadmap-delivery" / "automation.toml"
text = source.read_text(encoding="utf-8")
text = text.replace('cwds = ["."]', f'cwds = ["{repo}"]')
target.write_text(text, encoding="utf-8")
PY

AUTONOMOUS_ROADMAP_AUTOMATIONS_DIR="$SMOKE_HOME/.codex/automations" \
PYTHONPATH="$PWD/src" \
python3 -m roadmap_delivery.cli validate \
  --repo-root "$SMOKE_REPO" \
  --roadmap-slug demo-roadmap \
  --automation-id demo-roadmap-delivery \
  --json
```

The validate command should return nonzero and report
`automation_model_mismatch` plus `automation_reasoning_mismatch`.

Repair only the temporary saved config and validate again:

```bash
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

AUTONOMOUS_ROADMAP_AUTOMATIONS_DIR="$SMOKE_HOME/.codex/automations" \
PYTHONPATH="$PWD/src" \
python3 -m roadmap_delivery.cli validate \
  --repo-root "$SMOKE_REPO" \
  --roadmap-slug demo-roadmap \
  --automation-id demo-roadmap-delivery \
  --strict \
  --json
```

The repaired report should return `status: ok` and no findings.
