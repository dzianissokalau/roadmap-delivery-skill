# Demo Roadmap Fixture

This fixture is a tiny self-contained repository for trying the roadmap
delivery workflow without network access, credentials, or a live Codex app
automation.

It demonstrates:

- a roadmap with one delivered phase and one current phase
- committed automation state, log, review, policy, and run-log artifacts
- a scaffold dry-run that plans files without writing them
- validation and inspection of the file-backed control plane
- safe blocked-run and model-policy mismatch scenarios
- conservative fallback and delegated local approval-policy scenarios
- an install and runtime checklist for the generated Codex and Claude packages

## Demo A: Normal Evidence Trail

This path shows a clean local roadmap control plane with one delivered phase
and one current phase. Run it from the repository root:

```bash
python3 -m roadmap_delivery.cli validate \
  --repo-root examples/demo-roadmap \
  --roadmap-slug demo-roadmap \
  --json

python3 -m roadmap_delivery.cli inspect \
  --repo-root examples/demo-roadmap \
  --roadmap-slug demo-roadmap \
  --json
```

The direct commands may warn that no saved Codex automation config exists in
your local home directory. To see the same path with automation readback and no
home-directory mutation, copy the fixture into a temporary checkout and point
the CLI at the committed sample config:

```bash
export SMOKE_HOME="$(mktemp -d)"
export SMOKE_REPO="$SMOKE_HOME/demo-roadmap"
cp -R examples/demo-roadmap "$SMOKE_REPO"
git -C "$SMOKE_REPO" init -b codex/demo-roadmap-phase-1
git -C "$SMOKE_REPO" add .
git -C "$SMOKE_REPO" -c user.name=Demo -c user.email=demo.invalid \
  commit -m "demo fixture"
mkdir -p "$SMOKE_HOME/.codex/automations/demo-roadmap-delivery"
python3 - <<'PY'
from pathlib import Path
import os

repo = Path(os.environ["SMOKE_REPO"]).resolve()
home = Path(os.environ["SMOKE_HOME"])
source = repo / "automation-config" / "demo-roadmap-delivery" / "automation.toml"
target = home / ".codex" / "automations" / "demo-roadmap-delivery" / "automation.toml"
target.write_text(
    source.read_text(encoding="utf-8").replace('cwds = ["."]', f'cwds = ["{repo}"]'),
    encoding="utf-8",
)
PY

AUTONOMOUS_ROADMAP_AUTOMATIONS_DIR="$SMOKE_HOME/.codex/automations" \
python3 -m roadmap_delivery.cli inspect \
  --repo-root "$SMOKE_REPO" \
  --roadmap-slug demo-roadmap \
  --automation-id demo-roadmap-delivery \
  --strict \
  --json
```

Expected evidence fields include `current_phase`,
`last_delivered_phase`, `allowed_operations`, `required_model`,
`required_reasoning_effort`, `configured_automation_model`, and
`blocked_remediation_required: false`.

## Demo B: Policy Mismatch Then Repair

This path shows invalid advancement prevention without touching real
automation config. The first validation uses a temporary saved config with the
wrong model and reasoning effort; the second validation repairs only that
temporary config.

```bash
export SMOKE_HOME="$(mktemp -d)"
export SMOKE_REPO="$SMOKE_HOME/demo-roadmap"
cp -R examples/demo-roadmap "$SMOKE_REPO"
git -C "$SMOKE_REPO" init -b codex/demo-roadmap-phase-1
git -C "$SMOKE_REPO" add .
git -C "$SMOKE_REPO" -c user.name=Demo -c user.email=demo.invalid \
  commit -m "demo fixture"
mkdir -p "$SMOKE_HOME/.codex/automations/demo-roadmap-delivery"

python3 - <<'PY'
from pathlib import Path
import os

repo = Path(os.environ["SMOKE_REPO"]).resolve()
home = Path(os.environ["SMOKE_HOME"])
source = Path("examples/demo-roadmap/scenarios/model-policy-mismatch/automation.toml")
target = home / ".codex" / "automations" / "demo-roadmap-delivery" / "automation.toml"
target.write_text(
    source.read_text(encoding="utf-8").replace('cwds = ["."]', f'cwds = ["{repo}"]'),
    encoding="utf-8",
)
PY

AUTONOMOUS_ROADMAP_AUTOMATIONS_DIR="$SMOKE_HOME/.codex/automations" \
python3 -m roadmap_delivery.cli validate \
  --repo-root "$SMOKE_REPO" \
  --roadmap-slug demo-roadmap \
  --automation-id demo-roadmap-delivery \
  --json
```

The report should be nonzero and include `automation_model_mismatch` and
`automation_reasoning_mismatch`. Repair the temporary config by restoring the
sample readback:

```bash
python3 - <<'PY'
from pathlib import Path
import os

repo = Path(os.environ["SMOKE_REPO"]).resolve()
home = Path(os.environ["SMOKE_HOME"])
source = repo / "automation-config" / "demo-roadmap-delivery" / "automation.toml"
target = home / ".codex" / "automations" / "demo-roadmap-delivery" / "automation.toml"
target.write_text(
    source.read_text(encoding="utf-8").replace('cwds = ["."]', f'cwds = ["{repo}"]'),
    encoding="utf-8",
)
PY

AUTONOMOUS_ROADMAP_AUTOMATIONS_DIR="$SMOKE_HOME/.codex/automations" \
python3 -m roadmap_delivery.cli validate \
  --repo-root "$SMOKE_REPO" \
  --roadmap-slug demo-roadmap \
  --automation-id demo-roadmap-delivery \
  --strict \
  --json
```

The repaired report should be `status: ok` with no errors or warnings.

## Scaffold Dry Run

For a starter artifact preview that writes nothing:

```bash
python3 -m roadmap_delivery.cli scaffold \
  --repo-root "$(mktemp -d)/demo-roadmap-plan" \
  --roadmap-slug demo-roadmap \
  --automation-id demo-roadmap-delivery \
  --dry-run \
  --json
```

## Scenario Files

`scenarios/blocked-remediation/` contains a blocked Phase 1 state and review.
It shows the shape an automation should preserve when a local artifact is
missing: keep the run blocked, retain the reason, and enter Blocker Remediation
Mode on the next pass.

`scenarios/model-policy-mismatch/automation.toml` intentionally configures the
wrong model and reasoning effort. Validation should stop before delivery when
that saved automation config is used with the demo policy.

`scenarios/delegated-local/approval_policy.json` can be copied into
`automation/demo_roadmap/approval_policy.json` in a temporary checkout. Inspect
should then report `delegated_local`, allow local commits, model retargets, and
completion or stall pause, and keep branch push ask-first.

## Runtime Checklist

Use `runtime-checklist.md` to stage the generated Codex package and Claude
plugin in temporary directories, run inspect and validate on a temporary demo
checkout, trigger the delegated-local policy fixture, trigger the
blocked-remediation fixture, and trigger the model-policy-mismatch fixture
without credentials or live automation changes.
