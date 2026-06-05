import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CODEX_PACKAGE = REPO_ROOT / "skill" / "roadmap-delivery-skill"
CLAUDE_PACKAGE = REPO_ROOT / "dist" / "claude"
DEMO_ROOT = REPO_ROOT / "examples" / "demo-roadmap"
DEMO_SLUG = "demo-roadmap"
DEMO_AUTOMATION_ID = "demo-roadmap-delivery"
VERSION = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()


class InstallSmokeTests(unittest.TestCase):
    maxDiff = None

    def run_json(self, command, *, cwd=REPO_ROOT, env=None, allowed_returncodes=(0,)):
        proc = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertIn(proc.returncode, allowed_returncodes, proc.stderr or proc.stdout)
        try:
            return json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise AssertionError(proc.stderr or proc.stdout) from exc

    def copy_demo_repo(self, tmpdir):
        demo_repo = Path(tmpdir) / "demo-roadmap"
        shutil.copytree(DEMO_ROOT, demo_repo)
        subprocess.run(
            ["git", "init", "-b", "codex/demo-roadmap-phase-1"],
            cwd=demo_repo,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        subprocess.run(["git", "add", "."], cwd=demo_repo, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=Demo",
                "-c",
                "user.email=demo.invalid",
                "commit",
                "-m",
                "demo fixture",
            ],
            cwd=demo_repo,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return demo_repo

    def env_with_config(self, tmpdir, demo_repo, source):
        home = Path(tmpdir) / "home"
        automation_dir = home / ".codex" / "automations" / DEMO_AUTOMATION_ID
        automation_dir.mkdir(parents=True)
        text = source.read_text(encoding="utf-8")
        text = text.replace('cwds = ["."]', "cwds = [" + json.dumps(str(demo_repo)) + "]")
        (automation_dir / "automation.toml").write_text(text, encoding="utf-8")
        env = os.environ.copy()
        env["HOME"] = str(home)
        env["CODEX_HOME"] = str(home / ".codex")
        env["AUTONOMOUS_ROADMAP_AUTOMATIONS_DIR"] = str(home / ".codex" / "automations")
        env["PYTHONPYCACHEPREFIX"] = str(Path(tmpdir) / "pycache")
        env["PYTHONPATH"] = str(REPO_ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
        return env

    def test_codex_package_stages_in_temp_home_and_helpers_validate_demo(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_target = Path(tmp) / "home" / ".codex" / "skills" / "roadmap-delivery-skill"
            shutil.copytree(CODEX_PACKAGE, skill_target)
            demo_repo = self.copy_demo_repo(tmp)
            env = self.env_with_config(
                tmp,
                demo_repo,
                DEMO_ROOT / "automation-config" / DEMO_AUTOMATION_ID / "automation.toml",
            )

            required_files = (
                "SKILL.md",
                "agents/openai.yaml",
                "references/phase-loop.md",
                "scripts/inspect_delivery_state.py",
                "scripts/validate_delivery_artifacts.py",
            )
            for name in required_files:
                with self.subTest(path=name):
                    self.assertTrue((skill_target / name).is_file())

            inspect = self.run_json(
                [
                    sys.executable,
                    str(skill_target / "scripts" / "inspect_delivery_state.py"),
                    "--repo-root",
                    str(demo_repo),
                    "--roadmap-slug",
                    DEMO_SLUG,
                    "--automation-id",
                    DEMO_AUTOMATION_ID,
                    "--json",
                ],
                cwd=demo_repo,
                env=env,
            )
            validate = self.run_json(
                [
                    sys.executable,
                    str(skill_target / "scripts" / "validate_delivery_artifacts.py"),
                    "--repo-root",
                    str(demo_repo),
                    "--roadmap-slug",
                    DEMO_SLUG,
                    "--automation-id",
                    DEMO_AUTOMATION_ID,
                    "--strict",
                    "--json",
                ],
                cwd=demo_repo,
                env=env,
            )

            self.assertEqual(inspect["current_phase"], "Phase 1 - Add Smoke Checked Command")
            self.assertTrue(inspect["blocked_remediation_guard"])
            self.assertFalse(inspect["model_mismatch"])
            self.assertFalse(inspect["reasoning_mismatch"])
            self.assertEqual(validate["errors"], [])
            self.assertEqual(validate["warnings"], [])

    def test_claude_plugin_stages_and_cli_runtime_validates_demo(self):
        with tempfile.TemporaryDirectory() as tmp:
            plugin_target = Path(tmp) / "claude" / "plugins" / "roadmap-delivery"
            shutil.copytree(CLAUDE_PACKAGE, plugin_target)
            demo_repo = self.copy_demo_repo(tmp)
            env = self.env_with_config(
                tmp,
                demo_repo,
                DEMO_ROOT / "automation-config" / DEMO_AUTOMATION_ID / "automation.toml",
            )

            manifest = json.loads((plugin_target / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["name"], "roadmap-delivery")
            self.assertTrue((plugin_target / "skills" / "roadmap-delivery-skill" / "SKILL.md").is_file())
            self.assertTrue((plugin_target / "agents" / "reviewer.md").is_file())
            self.assertTrue((plugin_target / "hooks" / "hooks.json").is_file())

            inspect = self.run_json(
                [
                    sys.executable,
                    "-m",
                    "roadmap_delivery.cli",
                    "inspect",
                    "--repo-root",
                    str(demo_repo),
                    "--roadmap-slug",
                    DEMO_SLUG,
                    "--automation-id",
                    DEMO_AUTOMATION_ID,
                    "--strict",
                    "--json",
                ],
                cwd=REPO_ROOT,
                env=env,
            )
            validate = self.run_json(
                [
                    sys.executable,
                    "-m",
                    "roadmap_delivery.cli",
                    "validate",
                    "--repo-root",
                    str(demo_repo),
                    "--roadmap-slug",
                    DEMO_SLUG,
                    "--automation-id",
                    DEMO_AUTOMATION_ID,
                    "--strict",
                    "--json",
                ],
                cwd=REPO_ROOT,
                env=env,
            )

            self.assertEqual(inspect["status"], "ok")
            self.assertEqual(inspect["current_phase"], "Phase 1 - Add Smoke Checked Command")
            self.assertEqual(validate["status"], "ok")
            self.assertEqual(validate["warnings"], [])

    def test_release_artifacts_stage_offline_package_layouts(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "dist"
            report = self.run_json(
                [
                    sys.executable,
                    "scripts/build_release.py",
                    "--output-dir",
                    str(output_dir),
                    "--json",
                ]
            )
            artifacts = {item["kind"]: Path(item["path"]) for item in report["artifacts"]}

            codex_unpack = Path(tmp) / "codex-unpack"
            claude_unpack = Path(tmp) / "claude-unpack"
            shutil.unpack_archive(str(artifacts["codex_skill_package"]), codex_unpack)
            shutil.unpack_archive(str(artifacts["claude_plugin_package"]), claude_unpack)

            codex_package = codex_unpack / f"roadmap-delivery-codex-skill-{VERSION}"
            claude_package = claude_unpack / f"roadmap-delivery-claude-plugin-{VERSION}"
            self.assertTrue((codex_package / "SKILL.md").is_file())
            self.assertTrue((codex_package / "references" / "phase-loop.md").is_file())
            self.assertTrue((codex_package / "scripts" / "validate_delivery_artifacts.py").is_file())
            self.assertTrue((claude_package / ".claude-plugin" / "plugin.json").is_file())
            self.assertTrue((claude_package / "skills" / "roadmap-delivery-skill" / "SKILL.md").is_file())
            self.assertTrue((claude_package / "agents" / "reviewer.md").is_file())
            self.assertTrue((claude_package / "hooks" / "hooks.json").is_file())

    def test_runtime_docs_cover_required_install_and_manual_checks(self):
        codex_doc = (REPO_ROOT / "docs" / "installing-codex.md").read_text(encoding="utf-8")
        claude_doc = (REPO_ROOT / "docs" / "installing-claude.md").read_text(encoding="utf-8")
        checklist = (DEMO_ROOT / "runtime-checklist.md").read_text(encoding="utf-8")

        self.assertIn("python3 scripts/build_adapters.py --adapter codex --check", codex_doc)
        self.assertIn("python3 scripts/build_adapters.py --adapter claude --check", claude_doc)
        for text in (codex_doc, claude_doc, checklist):
            with self.subTest(document=text.splitlines()[0]):
                self.assertIn("inspect", text)
                self.assertIn("validate", text)
                self.assertIn("blocked-remediation", text)
                self.assertIn("model-policy-mismatch", text)
                self.assertIn("AUTONOMOUS_ROADMAP_AUTOMATIONS_DIR", text)
        self.assertIn("## Short Path", codex_doc)
        self.assertIn("## Verification Path", codex_doc)
        self.assertIn("scripts/host_smoke.py --host codex --isolated-home --json", codex_doc)
        self.assertIn("skipped", codex_doc)
        self.assertIn("## Rollback Or Cleanup", codex_doc)
        self.assertIn("## Short Path", claude_doc)
        self.assertIn("## Verification Path", claude_doc)
        self.assertIn("## Rollback Or Cleanup", claude_doc)
        for text in (codex_doc, claude_doc):
            with self.subTest(readiness_doc=text.splitlines()[0]):
                self.assertIn("## Marketplace Readiness Checklist", text)
                self.assertIn("Required metadata", text)
                self.assertIn("Package contents", text)
                self.assertIn("Compatibility limits", text)
                self.assertIn("Privacy limits", text)
                self.assertIn("Submission blockers", text)
                self.assertIn("Manual fallback", text)

    def test_adapter_report_records_marketplace_readiness(self):
        report = self.run_json(
            [
                sys.executable,
                "scripts/build_adapters.py",
                "--check",
                "--json",
            ]
        )

        self.assertEqual(report["status"], "ok")
        for adapter_report in report["reports"]:
            with self.subTest(adapter=adapter_report["adapter"]):
                readiness = adapter_report["marketplace_readiness"]
                self.assertEqual(readiness["status"], "ok", readiness)
                self.assertEqual(readiness["failures"], [])
                self.assertTrue(
                    any(item["name"] == "host capability metadata" for item in readiness["checks"]),
                    readiness,
                )

    @unittest.skipIf(shutil.which("codex") is None, "codex binary is not installed; offline package smoke covers layout")
    def test_optional_codex_binary_help_runs_with_temp_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = os.environ.copy()
            env["CODEX_HOME"] = str(Path(tmp) / ".codex")
            proc = subprocess.run(
                [shutil.which("codex"), "--help"],
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)

    @unittest.skipIf(shutil.which("claude") is None, "claude binary is not installed; offline plugin smoke covers layout")
    def test_optional_claude_binary_help_runs_with_temp_plugin_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = os.environ.copy()
            env["CLAUDE_PLUGIN_DIR"] = str(Path(tmp) / "claude" / "plugins")
            proc = subprocess.run(
                [shutil.which("claude"), "--help"],
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)


if __name__ == "__main__":
    unittest.main()
