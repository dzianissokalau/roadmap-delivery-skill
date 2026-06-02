# Release Install And Distribution Trust Roadmap

Status: Delivered
Current phase: Complete
Last updated: 2026-06-02
Next action: Run the final deep-review prompt from the GitHub review branch,
then make separate human merge and publication decisions.
Blocked by: None.

## Purpose

This roadmap turns the review recommendations about release trust,
installation, licensing, marketplace-native packaging, and public project
governance into a delivery plan.

Commercialisation, pricing, paid support, and hosted-service packaging are out
of scope. The target is a trustworthy open-source distribution surface, not a
commercial launch.

## Review Recommendations Addressed

- Publish the first tagged release with stable release notes, checksums, and
  install assets.
- Package and document marketplace-native installs for Claude and the most
  native install path possible for Codex.
- Add GitHub Discussions, issue templates, a public roadmap board, and
  contribution starter tasks.
- Clarify licensing and trademark usage for generated artifacts and
  host-specific packaging.
- Keep privacy, host-parity, and false-safety warnings visible in release and
  distribution surfaces.

## Automation Readiness

Recommended automation setup:

```text
ROADMAP_PATH=roadmaps/delivered_release_install_and_distribution_trust_roadmap.md
ROADMAP_SLUG=release-install-and-distribution-trust
AUTOMATION_DIR=automation/release-install-and-distribution-trust
AUTOMATION_ID=release-install-and-distribution-trust
INITIAL_MODEL=gpt-5.5
INITIAL_REASONING=xhigh
CADENCE=hourly
EXECUTION_ENVIRONMENT=local
```

The roadmap has release-adjacent work, so the automation must use conservative
or explicitly delegated delivery policy. Publishing tags, GitHub releases,
marketplace submissions, package registry uploads, changes to repository
visibility, and credential use require explicit human approval even when local
release assets can be prepared automatically.

## Strategic Outcome

Users should be able to understand which package to install, verify that a
release bundle is authentic enough for local use, see what each host package
does and does not support, and evaluate the project through clear public
governance surfaces.

The end state is a repository that is ready for a human-approved first tagged
release and marketplace/distribution submissions, with no accidental claim that
Codex or Claude vendors endorse the project.

## Design Principles

- Prefer deterministic local release artifacts over ad hoc packaging.
- Treat publication as a separate operator-approved action.
- Make install paths explicit for Codex, Claude, and generic host planning.
- Use vendor names only for compatibility and host-target description.
- Keep Apache-2.0 licensing visible while clarifying generated artifact reuse.
- Keep privacy and host-parity limits near the install and release surfaces.
- Make public contribution surfaces structured enough to invite useful issues
  without creating support obligations the project cannot meet.

## Target Repository Shape

Likely additions or updates:

```text
CHANGELOG.md
LICENSE
README.md
SECURITY.md
docs/
  installing-codex.md
  installing-claude.md
  adapters.md
  compatibility.md
  release-notes-0.1.0.md
  trademark-and-licensing.md
  release-process.md
.github/
  ISSUE_TEMPLATE/
    bug_report.yml
    roadmap_request.yml
    installation_help.yml
  DISCUSSION_TEMPLATE/
    ideas.yml
    show-and-tell.yml
  workflows/
    release-check.yml
scripts/
  build_release.py
  check_release_privacy.py
tests/
  test_release_builder.py
  test_privacy_sanitization.py
  test_install_smoke.py
roadmaps/
  delivered_release_install_and_distribution_trust_roadmap.md
```

Do not add commercial pricing, paid-plan language, sales copy, or hosted
control-plane commitments.

## Phase Model Guidance

```text
Phase 0: gpt-5.5 / xhigh
Phase 1: gpt-5.5 / xhigh
Phase 2: gpt-5.5 / high
Phase 3: gpt-5.5 / high
Phase 4: gpt-5.5 / medium
Phase 5: gpt-5.5 / xhigh
```

## Phase Overview

```text
Phase 0 - Release Trust Contract And Scope
Phase 1 - Licensing Trademark And Support Boundary
Phase 2 - Release Asset And Install Path Hardening
Phase 3 - Marketplace-Native Package Preparation
Phase 4 - Public Project Governance Surfaces
Phase 5 - Release Candidate Evidence And Closeout
```

## Phase 0 - Release Trust Contract And Scope

### Objective

Define what "release-ready" means for this project without publishing anything.
Turn the review recommendations into a concrete trust contract for release
assets, install docs, privacy checks, adapter parity claims, and human approval
boundaries.

### Owned Files

```text
roadmaps/delivered_release_install_and_distribution_trust_roadmap.md
docs/release-process.md
README.md
automation/README.md
```

### Inputs

- Deep research review recommendations.
- Current release builder and privacy checker behavior.
- Current install docs for Codex and Claude.
- Existing README compatibility matrix and operating model.
- Existing approval policy never-auto operations.

### Implementation Steps

1. Add `docs/release-process.md` describing local release preparation,
   verification, privacy gates, checksum expectations, and publication
   approval boundaries.
2. Define the minimum release candidate evidence bundle: release notes,
   manifest, checksums, adapter drift check, privacy scan, install smoke
   result, and known limitations.
3. Clarify that release creation is allowed only up to local asset preparation
   unless a human explicitly approves publication.
4. Add README links to the release process and this roadmap.
5. Add automation README notes that this roadmap is planned but not configured
   until setup artifacts exist.

### Acceptance Criteria

- Release-readiness language is specific enough to become a checklist.
- The repository distinguishes "local release candidate prepared" from
  "published release".
- Privacy and host-parity limits are visible near release guidance.
- No pricing, paid support, hosted-service, or sales-plan work is introduced.

### Required Verification

```bash
python3 scripts/build_release.py --check
python3 scripts/check_release_privacy.py --repo-root .
python3 -m unittest tests.test_release_builder tests.test_privacy_sanitization -v
git diff --check
```

### Non-Goals

- Creating a GitHub release.
- Pushing tags.
- Uploading marketplace or package registry artifacts.
- Adding commercial pricing or paid support commitments.

### Stop Conditions

- Stop if release publication, tag creation, or marketplace submission becomes
  necessary to satisfy the phase.
- Stop if release artifacts include automation evidence, local operator paths,
  credentials, or review transcripts.
- Stop if license or trademark claims require legal judgement beyond project
  compatibility guidance.

### Delivery Evidence

- Delivered on 2026-06-02.
- Review:
  `automation/release-install-and-distribution-trust/reviews/release-install-and-distribution-trust-phase-0-review-iteration-2.md`
- Required verification passed:
  `python3 scripts/build_release.py --check`,
  `python3 scripts/check_release_privacy.py --repo-root .`,
  `python3 -m unittest tests.test_release_builder tests.test_privacy_sanitization -v`,
  and `git diff --check`.
- Targeted checklist checks passed:
  `python3 scripts/build_adapters.py --check` and
  `python3 -m unittest tests.test_install_smoke -v`.

## Phase 1 - Licensing Trademark And Support Boundary

### Objective

Clarify Apache-2.0 usage, generated artifact licensing, vendor-name usage, and
support boundaries for host-specific packages.

### Owned Files

```text
docs/trademark-and-licensing.md
README.md
docs/installing-codex.md
docs/installing-claude.md
docs/adapters.md
dist/claude/README.md
adapters/claude/plugin.json.template
adapters/codex/README.md
```

### Inputs

- Current `LICENSE`.
- Current Claude plugin manifest license metadata.
- Current install docs and adapter docs.
- Compatibility notes for Codex, Claude, and generic adapters.

### Implementation Steps

1. Add a concise licensing and trademark guidance document.
2. State that project code and generated package snapshots are Apache-2.0
   unless a file says otherwise.
3. Clarify that Codex, Claude, OpenAI, and Anthropic names are used only to
   describe compatibility targets and do not imply endorsement.
4. Add support-boundary language: local package support, optional live smoke
   checks, and no guarantee of host feature parity beyond validated surfaces.
5. Link the guidance from install docs, adapter docs, and package README files.
6. Regenerate adapter/package snapshots if canonical or adapter template
   changes require it.

### Acceptance Criteria

- Users can tell what license applies to generated artifacts.
- Host-specific package docs avoid endorsement ambiguity.
- Compatibility claims are limited to tested and documented surfaces.
- The docs preserve the existing Apache-2.0 project posture.

### Required Verification

```bash
python3 scripts/build_adapters.py --check --json
python3 scripts/build_release.py --check
python3 -m unittest tests.test_adapter_parity tests.test_claude_plugin_package tests.test_release_builder -v
git diff --check
```

### Non-Goals

- Legal advice.
- Changing the project license.
- Registering trademarks or seeking vendor endorsement.
- Marketplace publication.

### Stop Conditions

- Stop if guidance would require a binding legal opinion.
- Stop if adapter metadata implies official vendor certification.
- Stop if generated package changes drift from canonical sources.

### Delivery Evidence

- Delivered on 2026-06-02.
- Review:
  `automation/release-install-and-distribution-trust/reviews/release-install-and-distribution-trust-phase-1-review-iteration-1.md`
- Required verification passed:
  `python3 scripts/build_adapters.py --check --json`,
  `python3 scripts/build_release.py --check`,
  `python3 -m unittest tests.test_adapter_parity tests.test_claude_plugin_package tests.test_release_builder -v`,
  and `git diff --check`.
- Targeted checks passed:
  `python3 -m unittest tests.test_install_smoke tests.test_quality_gates -v`.
- Retarget check passed: Phase 2 requires `gpt-5.5` / `high`, and saved
  automation readback remains `gpt-5.5` / `xhigh`, so no retarget is needed.

## Phase 2 - Release Asset And Install Path Hardening

### Objective

Make the local release assets and install paths feel stable, verifiable, and
repeatable for early users.

### Owned Files

```text
scripts/build_release.py
scripts/check_release_privacy.py
docs/release-notes-0.1.0.md
docs/release-process.md
docs/installing-codex.md
docs/installing-claude.md
README.md
tests/test_release_builder.py
tests/test_install_smoke.py
tests/test_privacy_sanitization.py
```

### Inputs

- Existing release artifact files under `dist/`.
- Current local release builder.
- Current Codex and Claude install smoke docs.
- Existing privacy and sanitization guide.

### Implementation Steps

1. Ensure the release manifest records package names, versions, checksums, and
   adapter capability summaries.
2. Make the release notes file the source of truth for first-release contents,
   limitations, and verification commands.
3. Harden install docs so each package has a short path, a verification path,
   and a rollback or cleanup note.
4. Add or update tests for deterministic release manifest/checksum behavior.
5. Add or update install smoke fixtures so local package structure checks can
   run without live Codex or Claude binaries.
6. Keep release bundles free of local automation artifacts and sensitive
   repository context.

### Acceptance Criteria

- Release asset names, version, manifest entries, and checksum output are
  stable across repeated builds.
- Install docs tell users how to verify the package before touching their
  active host configuration.
- Privacy checks fail on known sensitive surfaces and pass on clean release
  bundles.
- Local release assets can be prepared without publishing them.

### Required Verification

```bash
python3 scripts/build_release.py --check --json
python3 scripts/check_release_privacy.py --repo-root .
python3 -m unittest tests.test_release_builder tests.test_install_smoke tests.test_privacy_sanitization -v
git diff --check
```

### Non-Goals

- Hosted installer services.
- Package registry publication.
- Live host marketplace listing.
- Commercial release pages.

### Stop Conditions

- Stop if a release artifact includes `.git`, `.codex`, `automation/`,
  roadmap delivery evidence, local machine paths, credentials, or secrets.
- Stop if install docs require destructive changes to a user's active Codex or
  Claude home.
- Stop if checksum or manifest behavior is nondeterministic.

### Delivery Evidence

- Delivered on 2026-06-02.
- Review:
  `automation/release-install-and-distribution-trust/reviews/release-install-and-distribution-trust-phase-2-review-iteration-1.md`
- Required verification passed:
  `python3 scripts/build_release.py --check --json`,
  `python3 scripts/check_release_privacy.py --repo-root .`,
  `python3 -m unittest tests.test_release_builder tests.test_install_smoke tests.test_privacy_sanitization -v`,
  and `git diff --check`.
- The release manifest now records release-note provenance, package names,
  versions, checksums, sizes, and adapter capability summaries.
- Install docs now include short paths, verification paths, isolated staging,
  optional live-host checks, and rollback or cleanup guidance.
- Privacy checks reject prefixed and nested `automation/`, `roadmaps/`,
  `.git/`, and `.codex` bundle members while clean release-bound content
  passes.
- Retarget check passed: Phase 3 requires `gpt-5.5` / `high`, and saved
  automation readback remains `gpt-5.5` / `xhigh`, so no retarget is needed.

## Phase 3 - Marketplace-Native Package Preparation

### Objective

Prepare host-native distribution materials for Claude and Codex without
submitting or publishing them.

### Owned Files

```text
docs/installing-codex.md
docs/installing-claude.md
docs/adapters.md
docs/compatibility.md
adapters/claude/plugin.json.template
dist/claude/README.md
skill/roadmap-delivery-skill/SKILL.md
skill/roadmap-delivery-skill/scripts/
scripts/build_adapters.py
tests/test_adapter_parity.py
tests/test_claude_plugin_package.py
tests/test_install_smoke.py
```

### Inputs

- Current Codex skill package snapshot.
- Current Claude plugin package snapshot.
- Host capability metadata.
- Compatibility and install docs.
- Current package build tests.

### Implementation Steps

1. Audit package manifests, descriptions, and install docs against current host
   packaging conventions.
2. Add a marketplace-preparation checklist for each host: required metadata,
   package contents, compatibility limits, privacy limits, and submission
   blockers.
3. Ensure Codex and Claude install docs explain the most native available path
   first, then the manual fallback.
4. Keep generated package content synchronized with canonical core sources.
5. Add offline smoke checks for package layout, manifest fields, required
   references, helper script availability, and host capability metadata.
6. Record unsupported or optional live-host checks as warnings rather than
   hiding them.

### Acceptance Criteria

- The repository contains enough package metadata and documentation for a human
  to evaluate marketplace submission readiness.
- Codex and Claude packages remain generated from canonical sources.
- Host parity limits are documented beside marketplace-preparation guidance.
- No marketplace submission occurs during the phase.

### Required Verification

```bash
python3 scripts/build_adapters.py --check --json
python3 scripts/build_release.py --check --json
python3 -m unittest tests.test_adapter_parity tests.test_claude_plugin_package tests.test_install_smoke -v
git diff --check
```

### Non-Goals

- Submitting to a marketplace.
- Claiming official host endorsement.
- Adding paid distribution channels.
- Removing manual install fallback paths.

### Stop Conditions

- Stop if a host requires credentials, account changes, or submission actions.
- Stop if package metadata would overstate support for live automation,
  readback, hooks, or approval UX.
- Stop if generated snapshots drift from adapter inputs.

### Delivery Evidence

- Delivered on 2026-06-02.
- Review:
  `automation/release-install-and-distribution-trust/reviews/release-install-and-distribution-trust-phase-3-review-iteration-1.md`
- Required verification passed:
  `python3 scripts/build_adapters.py --check --json`,
  `python3 scripts/build_release.py --check --json`,
  `python3 -m unittest tests.test_adapter_parity tests.test_claude_plugin_package tests.test_install_smoke -v`,
  and `git diff --check`.
- Targeted Codex adapter verification passed:
  `python3 -m unittest tests.test_adapter_codex -v`.
- Retarget check passed: Phase 4 requires `gpt-5.5` / `medium`, and saved
  automation readback remains `gpt-5.5` / `xhigh`, so no retarget is needed.

## Phase 4 - Public Project Governance Surfaces

### Objective

Add low-friction public contribution and discussion surfaces that improve
project trust without creating commercial support obligations.

### Owned Files

```text
.github/ISSUE_TEMPLATE/
.github/DISCUSSION_TEMPLATE/
.github/PULL_REQUEST_TEMPLATE.md
.github/CODEOWNERS
README.md
docs/contributor-workflow.md
roadmaps/
```

### Inputs

- Existing contributor workflow.
- Existing roadmaps and roadmap status.
- Existing privacy and security policy.
- Review recommendation for Discussions, issue templates, public roadmap
  board, and starter tasks.

### Implementation Steps

1. Add issue templates for bug reports, installation help, roadmap requests,
   and documentation gaps.
2. Add a pull request template that asks contributors to state verification,
   privacy considerations, adapter drift status, and release impact.
3. Add discussion templates or docs for ideas, usage reports, and host
   compatibility reports.
4. Add a lightweight public roadmap index in README that distinguishes
   delivered, planned, and not-yet-configured roadmaps.
5. Add starter contribution tasks that are non-sensitive and do not require
   access to local automation evidence.
6. Make privacy reporting routes visible from issue and discussion guidance.

### Acceptance Criteria

- New contributors have structured entry points for issues, discussions, and
  PRs.
- Public templates discourage posting secrets, local paths, automation logs, or
  review transcripts.
- README shows planned roadmap tracks without implying delivery has started.
- The project does not promise guaranteed support response times.

### Required Verification

```bash
python3 -m unittest tests.test_quality_gates -v
git diff --check
```

### Non-Goals

- Paid support tiers.
- SLA language.
- Hosted roadmap boards requiring credentials.
- Community management automation beyond repository templates.

### Stop Conditions

- Stop if a template asks users to upload sensitive automation evidence.
- Stop if public-roadmap language implies committed dates or paid commitments.
- Stop if adding templates requires repository setting changes that cannot be
  made from local files.

### Delivery Evidence

- Delivered on 2026-06-02.
- Review:
  `automation/release-install-and-distribution-trust/reviews/release-install-and-distribution-trust-phase-4-review-iteration-1.md`
- Required verification passed:
  `python3 -m unittest tests.test_quality_gates -v` and `git diff --check`.
- Added issue templates for bug reports, installation help, roadmap requests,
  and documentation gaps.
- Added discussion templates for ideas, usage reports, and host compatibility
  observations.
- Added a pull request template covering verification, privacy, adapter drift,
  release impact, publication boundaries, and support limits.
- README now shows a public roadmap index with delivered, active, and planned
  not-yet-configured tracks without committed dates or support guarantees.
- Contributor workflow docs now list public entry points, safe starter tasks,
  and privacy reporting routes.
- No repository settings, credentials, publication, branch push, marketplace
  submission, hosted board, SLA, or paid support surface was added.
- Retarget check passed: Phase 5 requires `gpt-5.5` / `xhigh`, and saved
  automation readback remains `gpt-5.5` / `xhigh`, so no retarget is needed.

## Phase 5 - Release Candidate Evidence And Closeout

### Objective

Assemble the final evidence that the repository is ready for a human-approved
first tagged release, while keeping publication outside automation.

### Owned Files

```text
docs/release-process.md
docs/release-notes-0.1.0.md
README.md
CHANGELOG.md
automation/<roadmap-slug>/
roadmaps/delivered_release_install_and_distribution_trust_roadmap.md
```

### Inputs

- Completed phase review artifacts.
- Release builder output.
- Privacy scan output.
- Adapter drift check output.
- Install smoke output.
- Licensing/trademark guidance.
- Public project governance templates.

### Implementation Steps

1. Run full local release, privacy, adapter, and install smoke verification.
2. Update release notes and changelog with first-release contents and known
   limitations.
3. Record release candidate evidence in the automation review artifacts and
   delivery log.
4. Prepare a final deep review prompt covering release assets, install paths,
   licensing/trademark boundaries, public templates, privacy risk, and
   publication readiness.
5. Rename the roadmap to `delivered_...` only after every phase is delivered,
   verification passes, and final review prompt requirements are satisfied.
6. Leave actual tag creation, GitHub Release publication, and marketplace
   submission as explicit human-approved next actions.

### Acceptance Criteria

- A human can review release readiness from docs, manifest/checksum outputs,
  tests, privacy scan, and final review prompt.
- The roadmap is closed only after finalization evidence exists.
- Publication and marketplace submission remain blocked until explicitly
  approved by the operator.
- Commercialisation and pricing remain absent.

### Required Verification

```bash
python3 -m unittest discover -s tests -v
python3 scripts/build_adapters.py --check --json
python3 scripts/build_release.py --check --json
python3 scripts/check_release_privacy.py --repo-root .
git diff --check
```

### Non-Goals

- Publishing the release.
- Creating tags.
- Submitting marketplace packages.
- Announcing pricing or commercial terms.

### Stop Conditions

- Stop if final release evidence is incomplete.
- Stop if the final deep review prompt has not been prepared or explicitly
  waived by a human.
- Stop if release publication becomes necessary to satisfy acceptance criteria.

### Delivery Evidence

- Delivered on 2026-06-02.
- Review:
  `automation/release-install-and-distribution-trust/reviews/release-install-and-distribution-trust-phase-5-review-iteration-1.md`
- Final deep-review prompt:
  `automation/release-install-and-distribution-trust/final-deep-review-prompt.md`
- Required verification passed:
  `python3 -m unittest discover -s tests -v`,
  `python3 scripts/build_adapters.py --check --json`,
  `python3 scripts/build_release.py --check --json`,
  `python3 scripts/check_release_privacy.py --repo-root .`, and
  `git diff --check`.
- Full test suite result: 185 tests ran with 1 expected optional Claude binary
  smoke skipped because the binary is not installed.
- Release builder result: version `0.1.0` artifacts were reproducible across
  two builds, package artifact validators passed, and embedded privacy scan
  findings were 0.
- Privacy scan result: 125 files scanned, 0 findings, 0 errors.
- Completion state: completed. The operator manually paused the saved
  `release-install-and-distribution-trust` automation and readback reports
  `PAUSED`.
- GitHub review branch:
  https://github.com/dzianissokalau/roadmap-delivery-skill/tree/codex/release-install-and-distribution-trust-phase-5
- Direct final deep-review prompt:
  https://github.com/dzianissokalau/roadmap-delivery-skill/blob/codex/release-install-and-distribution-trust-phase-5/automation/release-install-and-distribution-trust/final-deep-review-prompt.md
- External deep-review result:
  `automation/release-install-and-distribution-trust/reviews/release-install-and-distribution-trust-final-deep-review-external.md`
- External deep-review verdict: `ready-for-human-merge-review`.
- External deep-review fixes: generated `.egg-info` / `.dist-info` metadata is
  excluded from source archives, and operator-local workspace paths are
  redacted from release-trust automation artifacts.
- Post-fix full test suite result: 188 tests ran with 1 expected optional
  Claude binary smoke skipped because the binary is not installed.

## Human Follow-Up

- The external deep review is complete and the two actionable findings are
  fixed. The operator approved pushing the branch and merging it to `main`.
- Decide separately whether to tag, publish a GitHub Release, submit
  marketplace packages, sync installed skills/plugins, or use credentials.
  None of those actions are implied by the merge.
