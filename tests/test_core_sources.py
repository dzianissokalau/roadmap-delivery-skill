import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CORE_ROOT = REPO_ROOT / "core"
SKILL_REFERENCES = REPO_ROOT / "skill" / "roadmap-delivery-skill" / "references"
AUTOMATION_TEMPLATE = REPO_ROOT / "automation" / "codex_phase_gated_delivery_automation_template.md"

ADAPTER_ONLY_REFERENCES = {}

REQUIRED_REFERENCE_FILES = {
    "setup-automation.md",
    "phase-loop.md",
    "review-and-fix.md",
    "state-log-and-branches.md",
    "finalization-and-promotion.md",
    "troubleshooting.md",
    "model-policy-and-stall-control.md",
    "phase-preflight.md",
}

REQUIRED_TEMPLATE_FILES = {
    "delivery_state.md",
    "delivery_log.md",
    "review_artifact.md",
    "automation_guide.md",
    "automation_prompt.md",
}

REQUIRED_PROMPT_FILES = {
    "adaptive_model_gate.md",
    "blocked_remediation.md",
    "model_policy_gate.md",
    "review_gate.md",
    "completion_hard_stop.md",
}

HOST_SPECIFIC_MARKERS = (
    "Codex app",
    "$CODEX_HOME",
    "skill/roadmap-delivery-skill",
    "codex exec",
)


class CoreSourceTests(unittest.TestCase):
    def test_every_skill_reference_has_core_source_or_adapter_reason(self):
        skill_reference_names = {path.name for path in SKILL_REFERENCES.glob("*.md")}
        core_reference_names = {path.name for path in (CORE_ROOT / "references").glob("*.md")}

        missing_mapping = skill_reference_names - core_reference_names - set(ADAPTER_ONLY_REFERENCES)
        self.assertEqual(set(), missing_mapping)

        stale_core_files = REQUIRED_REFERENCE_FILES - core_reference_names
        self.assertEqual(set(), stale_core_files)

    def test_core_templates_and_prompts_exist(self):
        template_names = {path.name for path in (CORE_ROOT / "templates").glob("*.md")}
        prompt_names = {path.name for path in (CORE_ROOT / "prompts").glob("*.md")}

        self.assertEqual(set(), REQUIRED_TEMPLATE_FILES - template_names)
        self.assertEqual(set(), REQUIRED_PROMPT_FILES - prompt_names)

    def test_core_references_are_host_neutral(self):
        for path in (CORE_ROOT / "references").glob("*.md"):
            with self.subTest(path=path):
                text = path.read_text(encoding="utf-8")
                self.assertIn("## Core Contract", text)
                self.assertIn("## Host Adapter Boundary", text)
                for marker in HOST_SPECIFIC_MARKERS:
                    self.assertNotIn(marker, text)

    def test_automation_template_points_to_core_sources(self):
        text = AUTOMATION_TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("core/references/", text)
        self.assertIn("core/templates/", text)
        self.assertIn("core/prompts/", text)

    def test_automation_prompt_handles_activation_before_generic_blocker(self):
        prompt = (CORE_ROOT / "templates" / "automation_prompt.md").read_text(encoding="utf-8")
        setup_reference = (SKILL_REFERENCES / "setup-automation.md").read_text(encoding="utf-8")

        activation_marker = "Before recording a generic mismatch blocker"
        blocker_marker = "record the blocker"
        normalized_prompt = " ".join(prompt.split())
        normalized_setup = " ".join(setup_reference.split())

        self.assertIn(activation_marker, prompt)
        self.assertIn("Do not stop just because the saved runner is ACTIVE", normalized_prompt)
        self.assertLess(prompt.index(activation_marker), prompt.index(blocker_marker))
        self.assertIn(activation_marker, setup_reference)
        self.assertIn("Do not stop just because the saved automation is ACTIVE", normalized_setup)

    def test_setup_references_require_approval_policy_artifact(self):
        references = {
            "core": CORE_ROOT / "references" / "setup-automation.md",
            "skill": SKILL_REFERENCES / "setup-automation.md",
            "codex-template": REPO_ROOT
            / "adapters"
            / "codex"
            / "templates"
            / "references"
            / "setup-automation.md",
        }

        for name, path in references.items():
            with self.subTest(reference=name):
                text = path.read_text(encoding="utf-8")
                artifact_list_start = text.index("automation/<roadmap-slug>/")
                artifact_list = text[artifact_list_start : text.index("```", artifact_list_start)]
                self.assertIn("approval_policy.json", artifact_list)
                self.assertIn("retarget_saved_automation", text)


if __name__ == "__main__":
    unittest.main()
