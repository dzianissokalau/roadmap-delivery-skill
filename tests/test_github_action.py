import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ACTION_DIR = REPO_ROOT / ".github" / "actions" / "roadmap-delivery-validate"
ACTION_YML = ACTION_DIR / "action.yml"
ACTION_README = ACTION_DIR / "README.md"
GITHUB_ACTION_DOC = REPO_ROOT / "docs" / "github-action.md"
REPORTS_PY = REPO_ROOT / "src" / "roadmap_delivery" / "reports.py"


EXPECTED_INPUTS = {
    "repo-root",
    "roadmap-slug",
    "automation-id",
    "roadmap-path",
    "automation-dir",
    "strict",
    "allow-warning",
    "privacy-scan",
    "adapter-check",
    "release-check",
    "review-evidence",
    "report-format",
    "report-file",
    "live-host-smoke",
    "live-hosts",
}

EXPECTED_OUTPUTS = {
    "validation-status",
    "warnings-count",
    "errors-count",
    "review-evidence-status",
    "adapter-status",
    "privacy-status",
    "release-status",
    "live-host-status",
    "skipped-live-hosts",
    "report-file",
}


def read_action() -> str:
    return ACTION_YML.read_text(encoding="utf-8")


def run_action_cli(*args: str, allowed_returncodes=(0,)) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        [sys.executable, "-m", "roadmap_delivery.cli", "github-action", *args],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode not in allowed_returncodes:
        raise AssertionError(proc.stderr or proc.stdout)
    return proc


def section_keys(text: str, section: str) -> set[str]:
    match = re.search(rf"^{section}:\n(?P<body>.*?)(?=^\S|\Z)", text, flags=re.MULTILINE | re.DOTALL)
    if not match:
        return set()
    return set(re.findall(r"^  ([a-z0-9-]+):\n", match.group("body"), flags=re.MULTILINE))


class GithubActionContractTests(unittest.TestCase):
    maxDiff = None

    def test_action_metadata_declares_stable_offline_contract(self):
        action = read_action()

        self.assertIn("name: Roadmap Delivery Validate", action)
        self.assertIn("using: composite", action)
        self.assertEqual(section_keys(action, "inputs"), EXPECTED_INPUTS)
        self.assertEqual(section_keys(action, "outputs"), EXPECTED_OUTPUTS)
        self.assertIn('default: "false"', action)
        self.assertIn("Reserved action-level opt-in; use the host-smoke workflow", action)

    def test_action_command_assembly_delegates_to_existing_offline_tools(self):
        action = read_action()
        reports = REPORTS_PY.read_text(encoding="utf-8")

        required_snippets = (
            "roadmap_delivery.cli",
            "github-action",
            "--repo-root",
            "--report-format",
        )
        for snippet in required_snippets:
            with self.subTest(snippet=snippet):
                self.assertIn(snippet, action)

        report_snippets = (
            '"roadmap_delivery.cli"',
            '"validate"',
            "scripts/build_adapters.py",
            "scripts/check_release_privacy.py",
            "scripts/build_release.py",
            "reserved-for-later-phase",
        )
        for snippet in report_snippets:
            with self.subTest(snippet=snippet):
                self.assertIn(snippet, reports)

        forbidden_snippets = (
            "${{ secrets.",
            "gh release",
            "twine upload",
            "npm publish",
            "git push",
            "~/.codex",
        )
        for snippet in forbidden_snippets:
            with self.subTest(snippet=snippet):
                self.assertNotIn(snippet, action)

    def test_action_truthy_helper_is_bash_32_compatible(self):
        action = read_action()

        self.assertNotIn("${1,,}", action)
        self.assertIn("tr '[:upper:]' '[:lower:]'", action)
        self.assertIn('printf \'%s\' "$1"', action)

    def test_action_docs_match_metadata_contract(self):
        readme = ACTION_README.read_text(encoding="utf-8")
        guide = GITHUB_ACTION_DOC.read_text(encoding="utf-8")

        for input_name in EXPECTED_INPUTS:
            with self.subTest(input=input_name):
                self.assertIn(f"`{input_name}`", readme)
                self.assertIn(f"`{input_name}`", guide)

        for output_name in EXPECTED_OUTPUTS:
            with self.subTest(output=output_name):
                self.assertIn(f"`{output_name}`", readme)
                self.assertIn(f"`{output_name}`", guide)

        self.assertIn("Strict mode is opt-in", guide)
        self.assertIn("does not require secrets", guide)

    def test_action_cli_writes_json_report_and_github_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            report_file = tmp_path / "action-report.json"
            output_file = tmp_path / "github-output.txt"

            proc = run_action_cli(
                "--repo-root",
                str(REPO_ROOT),
                "--roadmap-slug",
                "framework-core-and-release-readiness",
                "--automation-id",
                "framework-core-and-release-readiness",
                "--strict",
                "--allow-warning",
                "missing_automation_config,current_branch_name_mismatch,worktree_dirty",
                "--no-adapter-check",
                "--no-privacy-scan",
                "--no-release-check",
                "--report-format",
                "json",
                "--report-file",
                str(report_file),
                "--github-output",
                str(output_file),
                "--json",
            )
            stdout_report = json.loads(proc.stdout)
            file_report = json.loads(report_file.read_text(encoding="utf-8"))
            output_text = output_file.read_text(encoding="utf-8")

            self.assertEqual(stdout_report["status"], "passed")
            self.assertEqual(file_report["status"], "passed")
            self.assertEqual(file_report["outputs"]["validation-status"], "passed")
            self.assertEqual(file_report["outputs"]["adapter-status"], "not-requested")
            self.assertIn(f"report-file={report_file.resolve()}", output_text)
            self.assertIn("validation-status=passed", output_text)

    def test_action_cli_writes_text_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            report_file = tmp_path / "action-report.txt"
            output_file = tmp_path / "github-output.txt"

            proc = run_action_cli(
                "--repo-root",
                str(REPO_ROOT),
                "--roadmap-slug",
                "framework-core-and-release-readiness",
                "--automation-id",
                "framework-core-and-release-readiness",
                "--strict",
                "--allow-warning",
                "missing_automation_config,current_branch_name_mismatch,worktree_dirty",
                "--no-adapter-check",
                "--no-privacy-scan",
                "--no-release-check",
                "--report-format",
                "text",
                "--report-file",
                str(report_file),
                "--github-output",
                str(output_file),
            )
            report_text = report_file.read_text(encoding="utf-8")

            self.assertIn("status: passed", proc.stdout)
            self.assertIn("validation-status: passed", report_text)
            self.assertIn("adapter-status: not-requested", report_text)

    def test_action_cli_blocks_missing_validation_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            report_file = tmp_path / "missing-target.json"
            output_file = tmp_path / "github-output.txt"

            proc = run_action_cli(
                "--repo-root",
                str(REPO_ROOT),
                "--no-adapter-check",
                "--no-privacy-scan",
                "--no-release-check",
                "--report-format",
                "json",
                "--report-file",
                str(report_file),
                "--github-output",
                str(output_file),
                "--json",
                allowed_returncodes=(1,),
            )
            stdout_report = json.loads(proc.stdout)
            file_report = json.loads(report_file.read_text(encoding="utf-8"))

            self.assertEqual(stdout_report["status"], "failed")
            self.assertEqual(file_report["outputs"]["validation-status"], "blocked")
            self.assertEqual(file_report["outputs"]["review-evidence-status"], "blocked")
            self.assertIn("errors-count=1", output_file.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
