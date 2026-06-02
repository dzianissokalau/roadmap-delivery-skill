# Pull Request

## Scope

- Current roadmap or issue:
- Files or surfaces changed:
- Non-goals:

## Verification

- [ ] I ran the roadmap-required checks or explained why they do not apply.
- [ ] I ran targeted checks for the behavior changed.
- [ ] `git diff --check` passes.

## Privacy And Safety

- [ ] I did not include credentials, private paths, local automation logs,
      review transcripts, or sensitive release artifacts.
- [ ] Public examples are redacted and do not expose operator-local evidence.
- [ ] Security concerns are routed through `SECURITY.md` rather than public
      exploit details.

## Adapter And Release Impact

- [ ] Adapter or generated package changes include drift-check evidence, or no
      adapter output changed.
- [ ] Release, manifest, checksum, install, or privacy behavior changes include
      local verification evidence, or no release surface changed.
- [ ] Publication, tag pushes, marketplace submission, repository setting
      changes, credential use, and installed-tool synchronization were not
      performed without explicit approval.

## Support Boundary

- [ ] This PR does not add paid support, SLA, hosted-service, marketplace
      publication, or vendor-endorsement claims.
