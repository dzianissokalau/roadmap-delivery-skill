import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BUILD_SCRIPT = REPO_ROOT / "scripts" / "build_adapters.py"


class AdapterBuildSystemTests(unittest.TestCase):
    maxDiff = None

    def run_build(self, *args, allowed_returncodes=(0,)):
        proc = subprocess.run(
            [sys.executable, str(BUILD_SCRIPT), "--repo-root", str(REPO_ROOT), *args],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertIn(proc.returncode, allowed_returncodes, proc.stderr or proc.stdout)
        return json.loads(proc.stdout)

    def report_for(self, report, adapter):
        return next(item for item in report["reports"] if item["adapter"] == adapter)

    def test_check_renders_codex_and_claude_without_host_apps(self):
        report = self.run_build("--check", "--json")

        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["adapters"], ["codex", "claude"])

        codex = self.report_for(report, "codex")
        self.assertEqual(codex["status"], "ok")
        self.assertEqual(codex["check_mode"], "output")
        self.assertEqual(codex["diffs"], [])
        self.assertEqual(codex["capability_file"], "host-capabilities/codex.yaml")
        self.assertGreater(codex["file_count"], 5)

        claude = self.report_for(report, "claude")
        self.assertEqual(claude["status"], "ok")
        self.assertEqual(claude["check_mode"], "output")
        self.assertEqual(claude["capability_file"], "host-capabilities/claude.yaml")
        self.assertEqual(
            [item["path"] for item in claude["files"]],
            [
                ".claude-plugin/plugin.json",
                "README.md",
                "skills/roadmap-delivery-skill/SKILL.md",
                "agents/reviewer.md",
                "hooks/hooks.json",
                "hooks/roadmap_delivery_safety.py",
                "skills/roadmap-delivery-skill/references/finalization-and-promotion.md",
                "skills/roadmap-delivery-skill/references/model-policy-and-stall-control.md",
                "skills/roadmap-delivery-skill/references/network-blocker-remediation.md",
                "skills/roadmap-delivery-skill/references/phase-preflight.md",
                "skills/roadmap-delivery-skill/references/phase-loop.md",
                "skills/roadmap-delivery-skill/references/review-and-fix.md",
                "skills/roadmap-delivery-skill/references/setup-automation.md",
                "skills/roadmap-delivery-skill/references/state-log-and-branches.md",
                "skills/roadmap-delivery-skill/references/troubleshooting.md",
            ],
        )

    def test_output_root_snapshot_write_is_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = self.run_build("--write", "--output-root", tmp, "--json")
            second = self.run_build("--write", "--output-root", tmp, "--json")

            self.assertEqual(first["status"], "ok")
            self.assertEqual(second["status"], "ok")
            for adapter in ("codex", "claude"):
                with self.subTest(adapter=adapter):
                    first_files = self.report_for(first, adapter)["files"]
                    second_files = self.report_for(second, adapter)["files"]
                    self.assertEqual(first_files, second_files)
                    self.assertTrue((Path(tmp) / adapter).is_dir())

    def test_check_fails_when_generated_snapshot_output_is_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.run_build("--adapter", "claude", "--write", "--output-root", tmp, "--json")
            stale_file = Path(tmp) / "claude" / "README.md"
            stale_file.write_text("stale\n", encoding="utf-8")

            report = self.run_build(
                "--adapter",
                "claude",
                "--check",
                "--output-root",
                tmp,
                "--json",
                allowed_returncodes=(1,),
            )

        claude = self.report_for(report, "claude")
        self.assertEqual(report["status"], "drift")
        self.assertEqual(claude["status"], "drift")
        self.assertEqual(claude["diffs"][0]["kind"], "content")
        self.assertEqual(claude["diffs"][0]["path"], "README.md")

    def test_explicit_generic_adapter_renders_documentation_pack(self):
        report = self.run_build("--adapter", "generic", "--check", "--json")

        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["adapters"], ["generic"])
        generic = self.report_for(report, "generic")
        self.assertEqual(generic["status"], "ok")
        self.assertFalse(generic["output_committed"])
        self.assertEqual(generic["check_mode"], "render_only")
        self.assertEqual(generic["capability_file"], "host-capabilities/generic.yaml")
        self.assertEqual(generic["diffs"], [])
        self.assertEqual(generic["errors"], [])
        self.assertIn("README.md", {item["path"] for item in generic["files"]})
        self.assertIn("cli/install.md", {item["path"] for item in generic["files"]})
        self.assertIn("checklists/future-adapter.md", {item["path"] for item in generic["files"]})
        self.assertIn("schemas/delivery_state.schema.json", {item["path"] for item in generic["files"]})
        self.assertIn("workflow/phase-loop.md", {item["path"] for item in generic["files"]})

    def test_generic_output_root_generation_is_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = self.run_build("--adapter", "generic", "--write", "--output-root", tmp, "--json")
            second = self.run_build("--adapter", "generic", "--check", "--output-root", tmp, "--json")

            self.assertEqual(first["status"], "ok")
            self.assertEqual(second["status"], "ok")
            first_generic = self.report_for(first, "generic")
            second_generic = self.report_for(second, "generic")
            self.assertEqual(first_generic["files"], second_generic["files"])
            self.assertEqual(second_generic["diffs"], [])
            self.assertTrue((Path(tmp) / "generic" / "README.md").is_file())
            self.assertTrue((Path(tmp) / "generic" / "schemas" / "delivery_state.schema.json").is_file())


if __name__ == "__main__":
    unittest.main()
