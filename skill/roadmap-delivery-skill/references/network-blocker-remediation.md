# Network Blocker Remediation Reference

Use this reference before recording or preserving a generic network blocker for
a roadmap phase.

## Codex Network Probe Pattern

Codex may report `CODEX_SANDBOX_NETWORK_DISABLED=1` while direct terminal
`curl` can still reach public unauthenticated URLs. In that case, Python
network calls, browser automation, and Python-spawned `curl` can fail DNS even
though a plain shell command that starts with `curl` works.

Do not stop at the environment flag alone. Prove whether direct terminal
networking works before telling the operator to use another execution surface.

Run these checks from the current automation worktree:

```bash
printenv CODEX_SANDBOX_NETWORK_DISABLED
curl -I -L --max-time 15 https://example.com
curl -L --max-time 20 -D /tmp/codex-network-probe.headers -o /tmp/codex-network-probe.html -w 'PROBE\t%{http_code}\t%{url_effective}\t%{size_download}\t%{exitcode}\t%{errormsg}\n' https://example.com
```

Interpretation:

- If direct terminal `curl` succeeds, treat the blocker as repairable for
  public unauthenticated source recovery.
- If direct terminal `curl` fails too, keep or record a true permission-gated
  network blocker and rerun phase preflight so the operator sees every known
  mitigation.
- If Python/browser networking fails but direct terminal `curl` succeeds,
  record that as a network-surface limitation, not as a phase blocker.

## Safe Direct-Curl Pattern

When direct terminal `curl` works and the phase already has approval for public
source access:

- Keep the command invocation direct; do not run network fetches through Python,
  browser automation, shell command substitution, or Python-spawned subprocesses.
- Prefer a run-scoped `curl -K <config>` file when fetching many URLs.
- Store the config, status rows, response headers, raw bodies, rendered text or
  extracted text, structured extraction output, and final manifest under a
  run-scoped artifact directory.
- Use public source URLs from the current phase queue only.
- Do not use credentials, authenticated browser sessions, alternate evidence
  sources, publication, promotion, pushes, destructive git, or saved automation
  config edits unless separately approved.

For multi-target status capture, use curl's write-out file output instead of
shell redirection around a loop:

```bash
curl -L --max-time 30 \
  -D automation/<roadmap-slug>/network/<run-id>/combined_body_headers.txt \
  -w '%output{>>automation/<roadmap-slug>/network/<run-id>/body_status.tsv}BODY\t%{urlnum}\t%{remote_ip}\t%{http_code}\t%{url_effective}\t%{content_type}\t%{size_download}\t%{filename_effective}\t%{exitcode}\t%{errormsg}\n' \
  -o automation/<roadmap-slug>/network/<run-id>/raw/001-example.html \
  https://example.com
```

## Evidence Required Before Clearing A Network Blocker

Only clear `blocked_reason` after verification proves:

- the target queue count matches the phase contract,
- every target has an attempted/refused status,
- the manifest records final URL, HTTP status, content hash, artifact path, and
  failure reason or recovered status for every target,
- every recovered field has raw artifact, text or structured artifact,
  source URL, content hash, and extraction timestamp,
- redirected homepages and identity-conflict pages are not used as source
  evidence,
- every non-recovered target remains in the failure/refetch queue with a precise
  reason,
- the review verdict is `delivered`.

If static preflight still reports `network_disabled` for a past delivered phase,
repair the durable preflight artifact to explain that direct terminal `curl`
evidence delivered the phase, while preserving the warning that Python/browser
networking remains unavailable.

## When To Keep The Blocker

Keep state blocked and ask for the smallest missing human action when:

- direct terminal `curl` cannot reach a simple public probe URL,
- the phase lacks approval for live public source access,
- credentials or an authenticated browser session would be required,
- source terms or anti-bot behavior prevent responsible collection,
- the required collection would exceed current phase scope,
- destructive git, publication, promotion, branch push, or saved automation
  config edits would be required.
