# Roadmap Closeout Checklist

Use this checklist before marking a roadmap delivered, paused, superseded, or
otherwise complete.

## Checklist

- Update the roadmap header: `Status`, `Current phase`, `Last updated`,
  `Next action`, and `Blocked by`.
- Update `README.md` so the current roadmap section points to the current file
  and repeats the current status, phase, next action, and blocker.
- Update `automation/README.md` so the active roadmap table points to the
  current state file and phase.
- Update inbound links across project documentation and automation files.
- Keep automation artifacts under `automation/<roadmap_slug>/`.
- Do not delete unique state, log, or review content while moving automation
  machinery.
- Run roadmap-specific verification commands recorded in the delivery log.
- Run a stale-link scan with `rg -n` for old roadmap filenames or paths.
- Record backlog follow-ups in the roadmap or a replacement roadmap instead of
  leaving them only in review notes.


- Confirm distinct final deep-review prompt/artifact or explicit human waiver,
  final verification and delivered review before claiming completion.
- Resolve terminal pause before ordinary phase/model/migration gates. Write the
  local alert; use supported status-only host updates and preserve other settings.
- Confirm PAUSED readback and record the receipt, or record a concrete
  disabled/not-applicable/pending outcome. Do not repeat existing pause approval.
