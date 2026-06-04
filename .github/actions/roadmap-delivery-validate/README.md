# Roadmap Delivery Validate Action

This local composite action runs offline roadmap delivery validation from a
GitHub Actions checkout. It delegates to the repository CLI and helper scripts;
it does not create secrets, publish artifacts, enable schedules, or run live
host smoke checks by default.

## Usage

```yaml
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
      allow-warning: missing_automation_config,current_branch_name_mismatch
      adapter-check: 'true'
      privacy-scan: 'true'
```

The action runs from the source checkout through `python3 -m
roadmap_delivery.cli github-action`, so normal offline validation does not
require package publication or network access.

## Inputs

| Input | Default | Purpose |
| --- | --- | --- |
| `repo-root` | `.` | Repository checkout to validate. |
| `roadmap-slug` | empty | Roadmap slug for `roadmap_delivery.cli validate`. |
| `automation-id` | empty | Automation id when saved readback is available. |
| `roadmap-path` | empty | Contract metadata for future path-first validation. |
| `automation-dir` | empty | Contract metadata for the repository automation directory. |
| `strict` | `false` | Fail on unallowed validation warnings. |
| `allow-warning` | empty | Comma or newline separated warning codes allowed in strict mode. |
| `privacy-scan` | `true` | Run `scripts/check_release_privacy.py --json`. |
| `adapter-check` | `true` | Run `scripts/build_adapters.py --check --json`. |
| `release-check` | `false` | Run `scripts/build_release.py --check --json`. |
| `review-evidence` | `true` | Surface review artifact presence from validation results. |
| `report-format` | `text` | Write a `text` or `json` action report. |
| `report-file` | empty | Optional report output path. |
| `live-host-smoke` | `false` | Reserved action-level opt-in; use the host-smoke workflow for current live evidence. |
| `live-hosts` | empty | Reserved comma separated live host list. |

## Outputs

| Output | Values |
| --- | --- |
| `validation-status` | `passed`, `failed`, or `blocked` |
| `warnings-count` | Validation warning count |
| `errors-count` | Validation error count |
| `review-evidence-status` | `present`, `missing`, `not-requested`, or `blocked` |
| `adapter-status` | `passed`, `failed`, or `not-requested` |
| `privacy-status` | `passed`, `failed`, or `not-requested` |
| `release-status` | `passed`, `failed`, or `not-requested` |
| `live-host-status` | `not-requested`, `skipped`, `passed`, or `failed` |
| `skipped-live-hosts` | Comma separated skip reasons |
| `report-file` | Path to the written report |

## Reports

The action writes a text or JSON report. JSON reports include the validation
command, optional adapter, privacy, and release check commands, return codes,
parsed command output, host capability coverage metadata, and the output values
exported to GitHub Actions.

The same behavior can be tested locally:

```bash
python3 -m roadmap_delivery.cli github-action \
  --repo-root . \
  --roadmap-slug example-roadmap \
  --automation-id example-roadmap-delivery \
  --strict \
  --allow-warning missing_automation_config,current_branch_name_mismatch \
  --report-format json \
  --report-file /tmp/roadmap-delivery-validate.json
```

## Using In Another Repository

For an unpublished local action, copy or vendor
`.github/actions/roadmap-delivery-validate` into the consuming repository and
install this package from source before invoking the action. The consuming
workflow should pass its own `roadmap-slug` or `automation-id` and allow only
the warning codes that are expected for that checkout.

```yaml
steps:
  - uses: actions/checkout@v4
  - uses: actions/setup-python@v5
    with:
      python-version: '3.11'
  - run: python3 -m pip install -e vendor/roadmap-delivery
  - uses: ./vendor/roadmap-delivery/.github/actions/roadmap-delivery-validate
    with:
      repo-root: .
      roadmap-slug: team-roadmap
      automation-id: team-roadmap-delivery
      strict: 'true'
      adapter-check: 'true'
      privacy-scan: 'true'
      release-check: 'false'
```

## Boundaries

Default validation is offline. Action-level live host smoke inputs remain
reserved and report `skipped`; use `.github/workflows/host-smoke-nightly.yml`
for current opt-in Codex and Claude smoke evidence. Repository secrets, remote
scheduled workflow activation, publishing, promotion to `main`, and
marketplace publication remain out of scope.
