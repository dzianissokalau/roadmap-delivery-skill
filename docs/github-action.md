# GitHub Action Contract

The repository includes a local composite action at
`.github/actions/roadmap-delivery-validate`. The action makes offline
validation and review-evidence checks available from a GitHub Actions checkout
and is wired into repository CI for local validation.

The action is intentionally conservative: it delegates to the existing CLI and
helper scripts, defaults to offline validation, does not require secrets, and
does not run live host smoke checks directly. Current live-host evidence is
handled by `scripts/host_smoke.py` and the dispatch-only
`.github/workflows/host-smoke-nightly.yml` template.

## Source Of Truth

The action delegates validation behavior to the repository CLI and helper
scripts. It must not reimplement roadmap, state, review, privacy, adapter, or
release validation logic in shell glue.

Primary commands:

```bash
python3 -m roadmap_delivery.cli github-action
python3 -m roadmap_delivery.cli validate
python3 -m roadmap_delivery.cli inspect
python3 -m roadmap_delivery.cli package
python3 scripts/build_adapters.py --check --json
python3 scripts/build_release.py --check --json
python3 scripts/check_release_privacy.py --repo-root .
```

The default action mode is offline and must not require secrets.

## Inputs

| Input | Default | Purpose |
| --- | --- | --- |
| `repo-root` | `.` | Repository checkout to validate. |
| `roadmap-slug` | empty | Roadmap slug for validation and inspection. |
| `automation-id` | empty | Saved automation id when readback is available. |
| `roadmap-path` | empty | Explicit roadmap path retained as contract metadata for path-first validation. |
| `automation-dir` | empty | Explicit repository-local automation artifact directory retained as contract metadata. |
| `strict` | `false` | Treat validation warnings as blocking when not allowed. |
| `allow-warning` | empty | Comma or newline separated warning codes accepted for this run. |
| `privacy-scan` | `true` | Run release privacy guardrails. |
| `adapter-check` | `true` | Run adapter drift checks. |
| `release-check` | `false` | Run local release artifact checks without publication. |
| `review-evidence` | `true` | Inspect review artifacts and phase-gate evidence. |
| `report-format` | `text` | `text` or `json` report output. |
| `report-file` | empty | Optional file path for a copied action report. |
| `live-host-smoke` | `false` | Reserved action-level opt-in. Use the host-smoke workflow for current live Codex or Claude smoke evidence. |
| `live-hosts` | empty | Reserved list such as `codex,claude`; current live smoke selection happens in the host-smoke workflow inputs. |

Strict mode is opt-in. Future live-host inputs must stay opt-in. Missing live
prerequisites must be reported as skipped, not passed.

If neither `roadmap-slug` nor `automation-id` is provided, the action reports
`validation-status=blocked` because the current CLI requires a concrete offline
validation target. The `roadmap-path` and `automation-dir` inputs are contract
metadata until future path-first CLI work supports them as validation targets.

## Outputs

| Output | Meaning |
| --- | --- |
| `validation-status` | `passed`, `failed`, or `blocked`. |
| `warnings-count` | Number of warning findings reported by the CLI. |
| `errors-count` | Number of error findings reported by the CLI. |
| `review-evidence-status` | `present`, `missing`, `not-requested`, or `blocked`. |
| `adapter-status` | `passed`, `failed`, or `not-requested`. |
| `privacy-status` | `passed`, `failed`, or `not-requested`. |
| `release-status` | `passed`, `failed`, or `not-requested`. |
| `live-host-status` | `not-requested`, `skipped`, `passed`, or `failed`. |
| `skipped-live-hosts` | Comma separated host names skipped with reasons in the report. |
| `report-file` | Path to the text or JSON report written by the action. |

## Failure Semantics

The action must fail when required offline validation reports errors. Warnings
fail only when strict mode or the selected CLI command treats them as blocking.

The action must distinguish:

- validation errors
- validation warnings
- missing review evidence
- skipped live host checks
- failed live host checks
- release or privacy guardrail failures

An enabled live check that cannot start because prerequisites are missing is
`skipped`. An enabled live check that starts and fails is `failed`. Neither
case may be folded into a generic offline validation pass.

## Workflow Shape

The local action supports usage similar to:

```yaml
name: Roadmap Delivery Validation

on:
  pull_request:

permissions:
  contents: read

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - uses: ./.github/actions/roadmap-delivery-validate
        with:
          repo-root: .
          roadmap-slug: example-roadmap
          automation-id: example-roadmap-delivery
          strict: 'true'
          adapter-check: 'true'
          privacy-scan: 'true'
```

Repository CI uses the delivered framework roadmap as an offline target. The
workflow allows only known local validation warnings such as missing saved
automation config, current branch mismatch, and dirty worktree evidence from
local phase delivery. This does not enable remote scheduled workflows or
publication.

## Report Contract

The action writes a report file in `text` or `json` format and exposes the
outputs listed above. The JSON report includes command results for the
underlying CLI and helper script calls so reviewers can distinguish validation
errors, warnings, review evidence, adapter drift, privacy findings, release
checks, and skipped live host requests. It also includes host coverage metadata
from `host-capabilities/` so action evidence and compatibility claims can be
reviewed together without treating skipped live smoke checks as passed.

The action behavior is also available as a local CLI command:

```bash
python3 -m roadmap_delivery.cli github-action \
  --repo-root . \
  --roadmap-slug example-roadmap \
  --automation-id example-roadmap-delivery \
  --strict \
  --allow-warning missing_automation_config,current_branch_name_mismatch \
  --adapter-check \
  --privacy-scan \
  --report-format json \
  --report-file /tmp/roadmap-delivery-validate.json
```

To use the local action in another repository before publication, copy or
vendor `.github/actions/roadmap-delivery-validate`, install the package from
source in the workflow, and pass that repository's own roadmap slug or
automation id. For example, if this repository is vendored at
`vendor/roadmap-delivery`, install that source path and use the action from
that vendored directory. This does not require repository secrets or
marketplace publication.

## Non-Goals

The action must not:

- create repository secrets
- enable remote schedules
- publish a GitHub Marketplace action
- publish packages or releases
- push branches or promote to `main`
- install or sync global Codex skills or Claude plugins
- require live Codex or Claude host access for default validation
- claim CI can guarantee compliance, security, or runtime safety
