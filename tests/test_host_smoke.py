import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from roadmap_delivery.reports import build_host_coverage_report


REPO_ROOT = Path(__file__).resolve().parents[1]
HOST_SMOKE = REPO_ROOT / "scripts" / "host_smoke.py"
NIGHTLY_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "host-smoke-nightly.yml"


class HostSmokeTests(unittest.TestCase):
    maxDiff = None

    def run_smoke(self, *args, env=None, allowed_returncodes=(0,)):
        proc = subprocess.run(
            [sys.executable, str(HOST_SMOKE), *args],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            check=False,
        )
        self.assertIn(proc.returncode, allowed_returncodes, proc.stderr or proc.stdout)
        try:
            return json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise AssertionError(proc.stderr or proc.stdout) from exc

    def check_by_name(self, report, name):
        for item in report["checks"]:
            if item["name"] == name:
                return item
        raise AssertionError(f"missing check {name!r}: {report['checks']!r}")

    def test_codex_smoke_reports_skipped_when_binary_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            active_home = Path(tmp) / "active-codex-home"
            active_home.mkdir()
            env = os.environ.copy()
            env["CODEX_HOME"] = str(active_home)
            missing_binary = str(Path(tmp) / "missing-codex")

            report = self.run_smoke(
                "--host",
                "codex",
                "--isolated-home",
                "--codex-binary",
                missing_binary,
                "--json",
                env=env,
            )

            self.assertEqual(report["status"], "skipped")
            self.assertEqual(report["offline_status"], "passed")
            self.assertEqual(report["live_status"], "skipped")
            self.assertFalse(report["active_codex_home_used"])
            self.assertFalse(report["created_real_automation"])
            self.assertEqual(self.check_by_name(report, "package_layout")["status"], "passed")
            self.assertEqual(self.check_by_name(report, "temporary_codex_home")["status"], "passed")
            self.assertEqual(self.check_by_name(report, "demo_fixture_validation")["status"], "passed")
            self.assertEqual(self.check_by_name(report, "codex_binary_help")["status"], "skipped")
            self.assertEqual(list(active_home.iterdir()), [])

    def test_codex_smoke_runs_fake_binary_inside_temporary_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            active_home = Path(tmp) / "active-codex-home"
            active_home.mkdir()
            env_out = Path(tmp) / "codex-home-used.txt"
            fake_codex = Path(tmp) / "codex"
            fake_codex.write_text(
                "\n".join(
                    [
                        "#!/usr/bin/env python3",
                        "import os",
                        "from pathlib import Path",
                        "Path(os.environ['FAKE_CODEX_ENV_OUT']).write_text(",
                        "    os.environ.get('CODEX_HOME', ''), encoding='utf-8'",
                        ")",
                        "print('usage: codex fake')",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            fake_codex.chmod(0o755)
            env = os.environ.copy()
            env["CODEX_HOME"] = str(active_home)
            env["FAKE_CODEX_ENV_OUT"] = str(env_out)

            report = self.run_smoke(
                "--host",
                "codex",
                "--isolated-home",
                "--codex-binary",
                str(fake_codex),
                "--json",
                env=env,
            )

            self.assertEqual(report["status"], "passed")
            self.assertEqual(report["live_status"], "passed")
            self.assertEqual(self.check_by_name(report, "codex_binary_help")["status"], "passed")
            used_home = Path(env_out.read_text(encoding="utf-8"))
            self.assertEqual(used_home.name, ".codex")
            self.assertNotEqual(str(used_home), str(active_home))
            self.assertEqual(list(active_home.iterdir()), [])

    def test_codex_smoke_requires_isolated_home(self):
        report = self.run_smoke("--host", "codex", "--json", allowed_returncodes=(1,))

        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["offline_status"], "failed")
        self.assertEqual(self.check_by_name(report, "isolated_home")["reason"], "isolated_home_required")

    def test_claude_smoke_reports_skipped_when_binary_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            active_plugin_dir = Path(tmp) / "active-claude-plugins"
            active_plugin_dir.mkdir()
            env = os.environ.copy()
            env["CLAUDE_PLUGIN_DIR"] = str(active_plugin_dir)
            missing_binary = str(Path(tmp) / "missing-claude")

            report = self.run_smoke(
                "--host",
                "claude",
                "--isolated-home",
                "--claude-binary",
                missing_binary,
                "--json",
                env=env,
            )

            self.assertEqual(report["status"], "skipped")
            self.assertEqual(report["offline_status"], "passed")
            self.assertEqual(report["live_status"], "skipped")
            self.assertFalse(report["active_claude_config_used"])
            self.assertFalse(report["created_real_automation"])
            self.assertEqual(self.check_by_name(report, "plugin_layout")["status"], "passed")
            self.assertEqual(self.check_by_name(report, "plugin_manifest")["status"], "passed")
            self.assertEqual(self.check_by_name(report, "temporary_claude_plugin_dir")["status"], "passed")
            self.assertEqual(self.check_by_name(report, "demo_fixture_validation")["status"], "passed")
            self.assertEqual(self.check_by_name(report, "hook_guard")["status"], "passed")
            self.assertEqual(self.check_by_name(report, "claude_binary_help")["status"], "skipped")
            self.assertEqual(list(active_plugin_dir.iterdir()), [])

    def test_claude_smoke_runs_fake_binary_with_temporary_plugin_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            active_plugin_dir = Path(tmp) / "active-claude-plugins"
            active_plugin_dir.mkdir()
            env_out = Path(tmp) / "claude-plugin-dir-used.txt"
            fake_claude = Path(tmp) / "claude"
            fake_claude.write_text(
                "\n".join(
                    [
                        "#!/usr/bin/env python3",
                        "import os",
                        "from pathlib import Path",
                        "Path(os.environ['FAKE_CLAUDE_ENV_OUT']).write_text(",
                        "    os.environ.get('CLAUDE_PLUGIN_DIR', ''), encoding='utf-8'",
                        ")",
                        "print('usage: claude fake')",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            fake_claude.chmod(0o755)
            env = os.environ.copy()
            env["CLAUDE_PLUGIN_DIR"] = str(active_plugin_dir)
            env["FAKE_CLAUDE_ENV_OUT"] = str(env_out)

            report = self.run_smoke(
                "--host",
                "claude",
                "--isolated-home",
                "--claude-binary",
                str(fake_claude),
                "--json",
                env=env,
            )

            self.assertEqual(report["status"], "passed")
            self.assertEqual(report["live_status"], "passed")
            self.assertEqual(self.check_by_name(report, "claude_binary_help")["status"], "passed")
            used_plugin_dir = Path(env_out.read_text(encoding="utf-8"))
            self.assertEqual(used_plugin_dir.name, "plugins")
            self.assertNotEqual(str(used_plugin_dir), str(active_plugin_dir))
            self.assertEqual(list(active_plugin_dir.iterdir()), [])

    def test_claude_smoke_requires_isolated_home(self):
        report = self.run_smoke("--host", "claude", "--json", allowed_returncodes=(1,))

        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["offline_status"], "failed")
        self.assertEqual(self.check_by_name(report, "isolated_home")["reason"], "isolated_home_required")

    def test_opt_in_nightly_workflow_runs_isolated_host_smoke(self):
        workflow = NIGHTLY_WORKFLOW.read_text(encoding="utf-8")

        required_snippets = (
            "workflow_dispatch:",
            "run_codex:",
            "run_claude:",
            "scripts/host_smoke.py",
            "--host codex",
            "--host claude",
            "--isolated-home",
            "build_host_coverage_report",
            "host-smoke-reports/host-coverage.json",
            "actions/upload-artifact@v4",
        )
        for snippet in required_snippets:
            with self.subTest(snippet=snippet):
                self.assertIn(snippet, workflow)
        self.assertNotIn("\n  schedule:", workflow)
        self.assertNotIn("${{ secrets.", workflow)
        self.assertNotIn("~/.codex", workflow)

    def test_host_coverage_report_uses_metadata_and_keeps_skips_visible(self):
        report = build_host_coverage_report(
            REPO_ROOT,
            smoke_reports=[
                {
                    "host": "codex",
                    "status": "skipped",
                    "offline_status": "passed",
                    "live_status": "skipped",
                    "checks": [
                        {
                            "name": "codex_binary_help",
                            "status": "skipped",
                            "summary": "Codex binary is not available on PATH.",
                            "reason": "codex_binary_not_found",
                        }
                    ],
                }
            ],
        )
        by_host = {item["host"]: item for item in report["hosts"]}

        self.assertEqual(report["status"], "warning")
        self.assertEqual(report["counts"]["hosts"], 3)
        self.assertEqual(report["counts"]["skipped_live_checks"], 1)
        self.assertEqual(by_host["codex"]["live_smoke_status"], "optional_supported")
        self.assertEqual(by_host["codex"]["offline_parity"], "package_layout_helper_scripts_demo_fixture_validation")
        self.assertEqual(by_host["codex"]["live_status"], "skipped")
        self.assertEqual(
            report["skipped_live_checks"],
            [{"host": "codex", "check": "codex_binary_help", "reason": "codex_binary_not_found"}],
        )
        self.assertEqual(by_host["claude"]["live_smoke_status"], "optional_local_smoke")
        self.assertEqual(by_host["generic"]["live_smoke_status"], "host_specific_adapter_required")


if __name__ == "__main__":
    unittest.main()
