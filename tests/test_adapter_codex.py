import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BUILD_SCRIPT = REPO_ROOT / "scripts" / "build_adapters.py"
MANIFEST = REPO_ROOT / "adapters" / "codex" / "package_manifest.json"
SNAPSHOT = REPO_ROOT / "tests" / "snapshots" / "codex" / "package_snapshot.json"


class CodexAdapterGenerationTests(unittest.TestCase):
    maxDiff = None

    def run_build(self, *args):
        proc = subprocess.run(
            [
                sys.executable,
                str(BUILD_SCRIPT),
                "--repo-root",
                str(REPO_ROOT),
                "--adapter",
                "codex",
                *args,
                "--json",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)
        report = json.loads(proc.stdout)
        self.assertEqual(report["adapters"], ["codex"])
        codex = report["reports"][0]
        self.assertEqual(codex["adapter"], "codex")
        return report, codex

    def run_build_check(self):
        return self.run_build("--check")

    def test_build_check_has_no_generated_package_drift(self):
        report, codex = self.run_build_check()

        self.assertEqual(report["status"], "ok")
        self.assertEqual(codex["status"], "ok")
        self.assertEqual(codex["diffs"], [])
        self.assertEqual(codex["errors"], [])
        self.assertEqual(codex["check_mode"], "output")
        self.assertTrue(codex["output_committed"])
        self.assertEqual(codex["capability_file"], "host-capabilities/codex.yaml")
        self.assertEqual(codex["output_dir"], str(REPO_ROOT / "skill" / "roadmap-delivery-skill"))
        self.assertEqual(codex["marketplace_readiness"]["status"], "ok")

    def test_rendered_package_matches_snapshot(self):
        _, codex = self.run_build_check()
        snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))

        self.assertEqual(snapshot["schema_version"], 1)
        self.assertEqual(snapshot["adapter"], "codex")
        actual = [
            {
                key: value
                for key, value in item.items()
                if key in {"path", "sha256", "size", "mode", "core_source", "core_sha256", "core_size"}
            }
            for item in codex["files"]
        ]
        self.assertEqual(snapshot["files"], actual)

    def test_generated_package_includes_codex_router_agent_and_helper_scripts(self):
        _, codex = self.run_build_check()
        files = {item["path"]: item for item in codex["files"]}

        self.assertIn("SKILL.md", files)
        self.assertIn("agents/openai.yaml", files)
        for helper in (
            "scripts/compute_progress_signature.py",
            "scripts/inspect_delivery_state.py",
            "scripts/plan_automation_retarget.py",
            "scripts/validate_delivery_artifacts.py",
            "scripts/write_operator_alert.py",
        ):
            with self.subTest(helper=helper):
                self.assertIn(helper, files)

        self.assertEqual(files["scripts/inspect_delivery_state.py"]["mode"], "0755")
        self.assertEqual(files["scripts/plan_automation_retarget.py"]["mode"], "0755")
        self.assertEqual(files["scripts/validate_delivery_artifacts.py"]["mode"], "0755")

    def test_skill_top_level_policy_gates_are_packaged(self):
        self.run_build_check()
        skill = (REPO_ROOT / "skill" / "roadmap-delivery-skill" / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("## Policy Gates", skill)
        self.assertIn("approval_policy.json", skill)
        self.assertIn("adaptive_model_policy", skill)
        self.assertIn("pause_automation_on_completion", skill)
        self.assertIn("pause_automation_on_stall", skill)
        self.assertIn("completed_pending_pause", skill)

    def test_skill_records_package_readiness_boundary(self):
        self.run_build_check()
        skill = (REPO_ROOT / "skill" / "roadmap-delivery-skill" / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("## Package Readiness", skill)
        self.assertIn("local skill package", skill)
        self.assertIn("host capability metadata", skill)
        self.assertIn("marketplace submission", skill)
        self.assertIn("human-approved operations", skill)

    def test_output_root_regeneration_is_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_report, write_codex = self.run_build("--write", "--output-root", tmp)
            check_report, check_codex = self.run_build("--check", "--output-root", tmp)

            self.assertEqual(write_report["status"], "ok")
            self.assertEqual(check_report["status"], "ok")
            self.assertTrue((Path(tmp) / "codex" / "SKILL.md").is_file())
            self.assertEqual(write_codex["files"], check_codex["files"])
            self.assertEqual(check_codex["diffs"], [])

    def test_reference_templates_are_tied_to_core_sources(self):
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        reference_entries = [
            item for item in manifest["files"] if str(item.get("output", "")).startswith("references/")
        ]

        self.assertTrue(reference_entries)
        for item in reference_entries:
            with self.subTest(output=item["output"]):
                core_source = item.get("core_source")
                self.assertIsInstance(core_source, str)
                self.assertTrue((REPO_ROOT / core_source).exists())

    def test_cli_package_plan_reports_renderer_ready(self):
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "roadmap_delivery.cli",
                "package",
                "--repo-root",
                str(REPO_ROOT),
                "--adapter",
                "codex",
                "--dry-run",
                "--json",
            ],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)
        report = json.loads(proc.stdout)

        self.assertTrue(report["renderer_ready"])
        self.assertTrue(report["adapter_overlay_present"])


if __name__ == "__main__":
    unittest.main()
