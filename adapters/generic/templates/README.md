# Roadmap Delivery Generic Adapter Pack

This generated pack is a documentation artifact for future host adapter work.
It is not a supported runtime integration and does not claim support for
Continue, Cline, Roo Code, OpenHands, or another named host.

## Contents

- `workflow/` contains the host-neutral phase-gated delivery references.
- `schemas/` contains the local JSON contracts used by state, reviews, model
  policy, approval policy, provider roles, and automation run logs.
- `cli/install.md` explains the host-neutral CLI surface a future adapter can
  rely on.
- `checklists/future-adapter.md` records the minimum work before a new host can
  be treated as supported.
- `capabilities/generic.yaml` records the generic template capability boundary.

The workflow references carry the same safety contract as the Codex and Claude
packages: `approval_policy.json` decisions are conservative by default,
`adaptive_model_policy` affects only the next run after run quality is known,
and completion or stall self-pause uses trusted runner readback or a local
alert with an operator action. Generated policies default those safety pauses
on and use a two-run no-progress threshold unless setup overrides them.

## Support Boundary

Codex and Claude are the only concrete adapter packages in this roadmap. A
future host needs its own capability file, adapter metadata, generated output,
tests, smoke checks, compatibility notes, and release privacy coverage before
the project should describe it as supported.

Until a host-specific adapter proves model/reasoning readback, recurring
automation, and a status-only pause surface, the generic pack falls back to
repository validation, file-backed state/log/review artifacts, and local
operator alerts.
