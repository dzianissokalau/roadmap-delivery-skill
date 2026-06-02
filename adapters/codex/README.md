# Codex Adapter

This directory is the Codex adapter source for the committed skill package at
`skill/roadmap-delivery-skill/`. The shared adapter renderer treats this
package as the baseline generated Codex output.

The generated Codex package is an Apache-2.0 repository artifact. Codex and
OpenAI names in this directory are compatibility labels only and do not imply
endorsement, certification, sponsorship, or official vendor status. Keep support
claims tied to the generated package layout, helper scripts, documented install
flow, and repository validation checks.

The renderer uses `package_manifest.json` to combine host-neutral core sources
with Codex-specific templates. Reference entries in the manifest point to their
matching `core/references/` source so package generation fails if a canonical
workflow source is missing. The Codex templates preserve the current installed
skill behavior while ownership moves out of the installed-skill snapshot.
Provider-role guidance is kept in the Codex model-policy reference so role
names map to Codex `model` and `reasoning_effort` runner fields without
claiming prompt-only control.

Check generated output with:

```bash
python3 scripts/build_adapters.py --adapter codex --check
```

Apply regenerated output with:

```bash
python3 scripts/build_adapters.py --adapter codex --write
```

The legacy `scripts/build_codex_package.py` entrypoint remains available so
existing install and release instructions continue to work while the multi-host
adapter flow becomes the primary package renderer.

Intentional Codex-only behavior in this adapter:

- The generated package path remains `skill/roadmap-delivery-skill/`.
- `agents/openai.yaml` keeps the Codex-facing skill display metadata.
- Helper scripts remain under `skill/roadmap-delivery-skill/scripts/` for
  installed-skill compatibility.
- Codex app automation readback and `$CODEX_HOME` examples stay in
  Codex-specific references rather than the host-neutral core.
