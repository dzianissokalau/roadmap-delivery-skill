# Network Blocker Remediation Reference

## Core Contract

Use this reference before recording or preserving a generic network blocker for
a roadmap phase.

A host may expose multiple network surfaces. A single environment flag,
preflight warning, or failed runtime path does not always prove that every
approved network path is unavailable. Before stopping on a network blocker,
probe the lowest-risk direct public request surface available to the host and
record the result.

## Probe Order

For phases that require public unauthenticated network access:

1. Check the host's declared network-disabled signal or equivalent preflight
   evidence.
2. Run a simple public HEAD probe from the phase worktree when the host allows
   direct shell commands.
3. Run a simple public body download probe when the HEAD probe succeeds.
4. Compare direct shell results with higher-level runtime results such as
   language subprocesses, browser automation, SDKs, or API clients.

Interpretation:

- If a direct public probe succeeds, treat the blocker as locally repairable for
  public unauthenticated source recovery when the phase already has approval.
- If all approved network surfaces fail, keep or record a permission-gated
  network blocker and rerun phase preflight so the operator sees every known
  mitigation.
- If one network surface fails but another approved surface succeeds, record the
  failed surface as a limitation, not as a phase blocker.

## Safe Public Fetch Pattern

When a direct public request surface works and the phase already has approval:

- Keep fetches scoped to the current phase queue.
- Store request configuration, status rows, response headers, raw bodies or
  equivalent source artifacts, extracted text, structured extraction output,
  and final manifest under a run-scoped artifact directory.
- Do not use credentials, authenticated sessions, alternate evidence sources,
  publication, promotion, branch pushes, destructive git, or saved runner
  configuration edits unless separately approved.
- Use structured status capture rather than ad hoc console output.

## Evidence Required Before Clearing A Network Blocker

Only clear `blocked_reason` after verification proves:

- the target queue count matches the phase contract,
- every target has an attempted/refused status,
- the manifest records final URL, status code, content hash or equivalent
  artifact hash, artifact path, and failure reason or recovered status for every
  target,
- every recovered field has artifact-backed evidence, source URL, content hash
  or equivalent artifact hash, and extraction timestamp,
- redirected homepages and identity-conflict pages are not used as source
  evidence,
- every non-recovered target remains in the failure/refetch queue with a precise
  reason,
- the review verdict is `delivered`.

If static preflight still reports a network blocker for a past delivered phase,
repair the durable preflight artifact to cite the delivered evidence while
preserving any host-surface limitation warning.

## When To Keep The Blocker

Keep state blocked and ask for the smallest missing human action when:

- every approved direct public probe fails,
- the phase lacks approval for live public source access,
- credentials or an authenticated session would be required,
- source terms or anti-bot behavior prevent responsible collection,
- the required collection would exceed current phase scope,
- destructive git, publication, promotion, branch push, or saved runner
  configuration edits would be required.

## Host Adapter Boundary

Host adapters should replace the abstract "direct public request surface" with
the safest concrete command or tool available on that host. They must not infer
credential approval from a successful public probe, and they must keep
destructive, publication, promotion, branch push, and saved runner configuration
changes behind the normal approval policy gates.
