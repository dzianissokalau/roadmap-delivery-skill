import json
import subprocess
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BUILD_SCRIPT = REPO_ROOT / "scripts" / "build_adapters.py"
DIST_ROOT = REPO_ROOT / "dist" / "claude"
PLUGIN_MANIFEST = DIST_ROOT / ".claude-plugin" / "plugin.json"
SKILL_ROOT = DIST_ROOT / "skills" / "roadmap-delivery-skill"
SKILL_FILE = SKILL_ROOT / "SKILL.md"
REVIEWER_AGENT = DIST_ROOT / "agents" / "reviewer.md"
HOOK_CONFIG = DIST_ROOT / "hooks" / "hooks.json"
HOOK_SCRIPT = DIST_ROOT / "hooks" / "roadmap_delivery_safety.py"
REFERENCE_ROOT = SKILL_ROOT / "references"
CORE_REFERENCE_ROOT = REPO_ROOT / "core" / "references"
SNAPSHOT = REPO_ROOT / "tests" / "snapshots" / "claude" / "package_snapshot.json"
VERSION = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()

CORE_REFERENCES = (
    "finalization-and-promotion.md",
    "model-policy-and-stall-control.md",
    "phase-preflight.md",
    "phase-loop.md",
    "review-and-fix.md",
    "setup-automation.md",
    "state-log-and-branches.md",
    "troubleshooting.md",
)


class ClaudePluginPackageTests(unittest.TestCase):
    maxDiff = None

    def run_build_check(self):
        proc = subprocess.run(
            [
                sys.executable,
                str(BUILD_SCRIPT),
                "--repo-root",
                str(REPO_ROOT),
                "--adapter",
                "claude",
                "--check",
                "--json",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)
        report = json.loads(proc.stdout)
        self.assertEqual(report["adapters"], ["claude"])
        claude = report["reports"][0]
        self.assertEqual(claude["adapter"], "claude")
        return report, claude

    def generated_text_files(self):
        return sorted(path for path in DIST_ROOT.rglob("*") if path.is_file())

    def test_build_check_has_no_generated_plugin_drift(self):
        report, claude = self.run_build_check()

        self.assertEqual(report["status"], "ok")
        self.assertEqual(claude["status"], "ok")
        self.assertEqual(claude["diffs"], [])
        self.assertEqual(claude["errors"], [])
        self.assertEqual(claude["check_mode"], "output")
        self.assertTrue(claude["output_committed"])
        self.assertEqual(claude["output_dir"], str(DIST_ROOT))
        self.assertEqual(claude["marketplace_readiness"]["status"], "ok")

    def test_manifest_declares_minimal_plugin_identity(self):
        self.run_build_check()
        manifest = json.loads(PLUGIN_MANIFEST.read_text(encoding="utf-8"))

        self.assertEqual(manifest["name"], "roadmap-delivery")
        self.assertEqual(manifest["displayName"], "Roadmap Delivery Skill")
        self.assertEqual(manifest["version"], VERSION)
        self.assertEqual(manifest["license"], "Apache-2.0")
        self.assertIsInstance(manifest["description"], str)
        self.assertTrue(manifest["description"])
        self.assertIn("file-backed", manifest["description"])
        self.assertEqual(set(path.name for path in PLUGIN_MANIFEST.parent.iterdir()), {"plugin.json"})

    def test_skill_and_core_references_are_generated(self):
        _, claude = self.run_build_check()
        files = {item["path"]: item for item in claude["files"]}

        self.assertIn(".claude-plugin/plugin.json", files)
        self.assertIn("skills/roadmap-delivery-skill/SKILL.md", files)
        self.assertIn("agents/reviewer.md", files)
        self.assertIn("hooks/hooks.json", files)
        self.assertIn("hooks/roadmap_delivery_safety.py", files)
        for name in CORE_REFERENCES:
            with self.subTest(reference=name):
                output = f"skills/roadmap-delivery-skill/references/{name}"
                self.assertIn(output, files)
                self.assertEqual(files[output]["core_source"], f"core/references/{name}")
                generated = (REFERENCE_ROOT / name).read_text(encoding="utf-8")
                core = (CORE_REFERENCE_ROOT / name).read_text(encoding="utf-8")
                if name == "phase-preflight.md":
                    self.assertIn("## Claude Manual Procedure", generated)
                    self.assertIn("## Core Contract", generated)
                    self.assertNotEqual(generated, core)
                else:
                    self.assertEqual(generated, core)

    def test_skill_preserves_core_phase_gate_safety_rules(self):
        self.run_build_check()
        skill = SKILL_FILE.read_text(encoding="utf-8")

        self.assertIn("Work exactly one roadmap phase at a time.", skill)
        self.assertIn("When state is `blocked`, try blocked-run remediation", skill)
        self.assertIn("Run required verification before claiming delivery.", skill)
        self.assertIn("Require a fresh review verdict before phase advancement.", skill)
        self.assertIn("Do not promote, merge, push, publish", skill)
        self.assertIn("## Claude Tool Permission Notes", skill)
        self.assertIn("Use the `roadmap-delivery-reviewer` agent for the review gate", skill)

    def test_skill_and_readme_package_policy_fallbacks(self):
        self.run_build_check()
        skill = SKILL_FILE.read_text(encoding="utf-8")
        readme = (DIST_ROOT / "README.md").read_text(encoding="utf-8")

        for term in (
            "## Policy Gates",
            "approval_policy.json",
            "adaptive_model_policy",
            "pause_automation_on_completion",
            "pause_automation_on_stall",
            "completed_pending_pause",
        ):
            with self.subTest(term=term):
                self.assertIn(term, skill)

        self.assertIn("conservative fallbacks", readme)
        self.assertIn("status-only pause surfaces", readme)
        self.assertIn("local alerts", readme)

    def test_package_readme_records_marketplace_readiness_boundary(self):
        self.run_build_check()
        skill = SKILL_FILE.read_text(encoding="utf-8")
        readme = (DIST_ROOT / "README.md").read_text(encoding="utf-8")

        for text in (skill, readme):
            with self.subTest(document=text.splitlines()[0]):
                lowered = text.lower()
                self.assertIn("marketplace", lowered)
                self.assertIn("host capability metadata", lowered)
                self.assertIn("privacy limits", lowered)
                self.assertIn("submission blockers", lowered)
                self.assertIn("human approval", lowered)

    def test_reviewer_agent_is_read_only_and_enforces_review_gate(self):
        self.run_build_check()
        agent = REVIEWER_AGENT.read_text(encoding="utf-8")

        self.assertIn("name: roadmap-delivery-reviewer", agent)
        self.assertIn("tools: Read, Glob, Grep", agent)
        self.assertIn("Do not edit files", agent)
        self.assertIn("acceptance criteria", agent)
        self.assertIn("If you find a problem, report it", agent)
        self.assertIn("executor", agent)
        self.assertIn("`delivered`", agent)
        self.assertIn("`needs-fix`", agent)
        self.assertIn("`blocked`", agent)
        self.assertNotIn("Edit", agent)
        self.assertNotIn("Write", agent)

    def test_hook_files_reinforce_core_safety_rules(self):
        self.run_build_check()
        hooks = json.loads(HOOK_CONFIG.read_text(encoding="utf-8"))
        script = HOOK_SCRIPT.read_text(encoding="utf-8")

        self.assertIn("Roadmap Delivery safety hooks", hooks["description"])
        self.assertIn("PreToolUse", hooks["hooks"])
        self.assertIn("UserPromptSubmit", hooks["hooks"])
        self.assertIn("Stop", hooks["hooks"])
        self.assertIn("destructive git reset", script)
        self.assertIn("broad git staging", script)
        self.assertIn("Blocked Remediation Mode", script)
        self.assertIn("Roadmap Delivery hard stop", script)
        self.assertIn("privacy reminder", script)

    def test_rendered_package_matches_snapshot(self):
        _, claude = self.run_build_check()
        snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))

        self.assertEqual(snapshot["schema_version"], 1)
        self.assertEqual(snapshot["adapter"], "claude")
        actual = [
            {
                key: value
                for key, value in item.items()
                if key in {"path", "sha256", "size", "mode", "core_source", "core_sha256", "core_size"}
            }
            for item in claude["files"]
        ]
        self.assertEqual(snapshot["files"], actual)

    def test_generated_claude_files_have_no_codex_only_runtime_paths(self):
        self.run_build_check()
        forbidden = (
            "~/.codex",
            "/.codex/",
            "skill/roadmap-delivery-skill",
            "agents/openai.yaml",
            "codex exec",
        )

        for path in self.generated_text_files():
            text = path.read_text(encoding="utf-8")
            for pattern in forbidden:
                with self.subTest(path=path.relative_to(DIST_ROOT).as_posix(), pattern=pattern):
                    self.assertNotIn(pattern, text)


if __name__ == "__main__":
    unittest.main()
