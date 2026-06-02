# Evidence Benchmark Demo

This directory documents the repository-local evidence benchmark harness. The
harness measures fixture evidence from `examples/demo-roadmap/` and reports
only local control-plane outcomes.

## Run

From the repository root:

```bash
python3 -m roadmap_delivery.cli benchmark \
  --repo-root . \
  --json \
  --output /tmp/roadmap-delivery-evidence-benchmark.json
```

The command copies the demo fixture into temporary repositories and creates
temporary saved automation configs. It does not edit the live fixture, use a
real Codex automation, require credentials, or publish telemetry.

## Evidence Fields

The normal evidence trail exposes these fields through `inspect`, `validate`,
and the benchmark report:

- `current_phase`
- `last_delivered_phase`
- `allowed_operations`
- `required_model`
- `required_reasoning_effort`
- `configured_automation_model`
- `configured_automation_reasoning_effort`
- `blocked_remediation_required`
- `detected_issues`
- `evidence_checks`
- `scores`
- `commands`

## Scenarios

The harness currently measures:

- clean delivery evidence
- missing review artifact
- stale lifecycle filename
- mismatched automation status
- insufficient verification evidence

The measured result at implementation time is:

```text
invalid advancement caught: 4 of 4
invalid advancement caught by validation errors: 1
evidence completeness score: 7 of 10
clean-fixture false-positive warnings: 0
```

## Boundaries

- no productivity or ROI claim
- no performance benchmark
- no external telemetry
- no hosted demo dependency
- no vendor comparison claim
