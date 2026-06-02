# Trademark And Licensing

This guide explains the repository's licensing, generated artifact, vendor-name,
and support boundaries. It is project guidance for maintainers and users; it is
not legal advice.

## License Scope

Roadmap Delivery Skill is licensed under the Apache License, Version 2.0. See
`LICENSE` for the license text.

Unless a file says otherwise, the Apache-2.0 project license applies to:

- source code, scripts, schemas, and documentation in this repository
- Codex package snapshots under `skill/roadmap-delivery-skill/`
- Claude plugin snapshots under `dist/claude/`
- local release archives generated from those repository files
- adapter templates and generated package metadata

Generated package snapshots do not add a separate license layer. They are
repository artifacts built from Apache-2.0 sources, so users may inspect, copy,
modify, and redistribute them under the same license terms while preserving
required license notices.

## Generated Artifact Notices

Generated artifacts should keep license metadata visible where the target host
supports it. For example, the Claude plugin manifest declares
`"license": "Apache-2.0"`, and release bundles include the repository license
file through the source and package archives.

If a future adapter requires host-specific manifest fields, keep the license
value explicit and do not imply that the host vendor grants additional rights
unless the vendor's own terms say so.

## Vendor Name Usage

The names Codex, OpenAI, Claude, Claude Code, and Anthropic are used only to
identify compatibility targets, install locations, or host-specific packaging
surfaces.

Do not describe this project or its generated packages as official,
certified, endorsed, sponsored, or approved by OpenAI, Anthropic, or any other
host vendor. Do not use vendor logos or marketplace branding unless that use is
allowed by the vendor's current trademark rules and has been reviewed by a
human maintainer.

Marketplace listings, release notes, README copy, adapter docs, and install
docs should use neutral compatibility language such as "Codex package",
"Claude plugin package", "for use with", or "compatible package". Avoid
phrasing that could be read as vendor certification.

## Support Boundary

The maintained support boundary is local and evidence-based:

- package layout and generated output are checked by repository tests
- adapter parity is limited to documented, generated surfaces
- install smoke tests stage packages in temporary homes or plugin directories
- live Codex or Claude binary checks are optional maintainer smoke checks
- publication, marketplace submission, and installed global package sync require
  explicit human approval

Compatibility claims are limited to tested and documented surfaces. The project
does not guarantee that every host feature, recurring automation surface,
model/reasoning readback field, hook behavior, approval UX, or plugin-loading
path has exact parity across Codex, Claude, and future hosts.

If a host changes its plugin, skill, automation, or permission model, treat the
change as a compatibility update: document the new boundary, update capability
metadata, run adapter and release checks, and avoid claiming support until the
evidence is current.

## Maintainer Checklist

Before changing release, install, adapter, or marketplace-facing copy, confirm:

- Apache-2.0 remains the stated license unless the project license changes
- generated artifact license metadata still matches `LICENSE`
- vendor names are descriptive compatibility labels only
- no package copy claims official vendor endorsement or certification
- support claims cite deterministic local checks or clearly marked optional live
  smoke checks
- publication and installed package sync remain human-approved operations
