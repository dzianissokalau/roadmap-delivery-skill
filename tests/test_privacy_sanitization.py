import json
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "check_release_privacy.py"


class PrivacySanitizationTests(unittest.TestCase):
    maxDiff = None

    def run_scanner(self, *args, cwd=None):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            cwd=cwd or REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def parse_json(self, result):
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            self.fail(f"scanner did not emit JSON: {exc}\nstdout={result.stdout}\nstderr={result.stderr}")

    def test_current_release_bound_files_pass_privacy_scan(self):
        result = self.run_scanner("--repo-root", str(REPO_ROOT), "--json")

        report = self.parse_json(result)
        self.assertEqual(result.returncode, 0, report)
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["findings"], [])
        self.assertGreater(report["files_scanned"], 20)

    def test_scanner_detects_unsanitized_local_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "README.md").write_text(
                "Do not publish /Users/alice/project/private-state.md\n",
                encoding="utf-8",
            )

            result = self.run_scanner(
                "--repo-root",
                str(root),
                "--release-path",
                "README.md",
                "--json",
            )

        report = self.parse_json(result)
        self.assertEqual(result.returncode, 1, report)
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["findings"][0]["code"], "local_absolute_path")
        self.assertEqual(report["findings"][0]["path"], "README.md")

    def test_scanner_detects_obvious_secret_shapes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "README.md").write_text(
                "Do not publish AKIAIOSFODNN7EXAMPLE\n",
                encoding="utf-8",
            )

            result = self.run_scanner(
                "--repo-root",
                str(root),
                "--release-path",
                "README.md",
                "--json",
            )

        report = self.parse_json(result)
        self.assertEqual(result.returncode, 1, report)
        self.assertEqual(report["findings"][0]["code"], "aws_access_key")
        self.assertEqual(report["findings"][0]["match"], "<redacted>")

    def test_release_trust_automation_artifacts_redact_operator_paths(self):
        automation_dir = REPO_ROOT / "automation" / "release-install-and-distribution-trust"
        self.assertTrue(automation_dir.is_dir(), automation_dir)
        checked = []

        for path in sorted(automation_dir.rglob("*")):
            if path.is_file() and path.suffix in {".json", ".md", ".jsonl"}:
                checked.append(path.relative_to(REPO_ROOT).as_posix())
                text = path.read_text(encoding="utf-8")
                self.assertNotIn("/Users/", text, path)

        self.assertGreater(len(checked), 10)

    def test_bundle_scan_rejects_forbidden_release_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            leaked_file = root / "private.md"
            leaked_file.write_text("local automation evidence\n", encoding="utf-8")
            for arcname in (
                "automation/private.md",
                "roadmap-delivery-0.2.0/automation/private.md",
                "roadmap-delivery-0.2.0/roadmaps/private.md",
                "roadmap-delivery-0.2.0/.git/config",
            ):
                with self.subTest(arcname=arcname):
                    bundle = root / f"{arcname.replace('/', '-')}.tar.gz"
                    with tarfile.open(bundle, "w:gz") as archive:
                        archive.add(leaked_file, arcname=arcname)

                    result = self.run_scanner(
                        "--repo-root",
                        str(root),
                        "--release-path",
                        "README.md",
                        "--bundle",
                        str(bundle),
                        "--json",
                    )

                    report = self.parse_json(result)
                    self.assertEqual(result.returncode, 1, report)
                    self.assertEqual(report["findings"][0]["code"], "forbidden_bundle_path")
                    self.assertEqual(report["findings"][0]["path"], arcname)

    def test_ci_and_docs_reference_privacy_guardrails(self):
        workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        security = (REPO_ROOT / "SECURITY.md").read_text(encoding="utf-8")
        privacy = (REPO_ROOT / "docs" / "privacy-and-sanitization.md").read_text(encoding="utf-8")
        release_check = (REPO_ROOT / ".github" / "workflows" / "release-check.yml").read_text(encoding="utf-8")
        release_builder = (REPO_ROOT / "scripts" / "build_release.py").read_text(encoding="utf-8")

        self.assertIn("python3 scripts/check_release_privacy.py --repo-root .", workflow)
        self.assertIn("SECURITY.md", readme)
        self.assertIn("docs/privacy-and-sanitization.md", readme)
        self.assertIn("python3 scripts/build_release.py --check", release_check)
        self.assertIn('"SECURITY.md"', release_builder)
        self.assertIn('"dist/claude"', release_builder)
        self.assertIn('"host-capabilities"', release_builder)
        self.assertIn('"CHANGELOG.md"', release_builder)
        self.assertIn('"docs"', release_builder)
        self.assertIn("Reporting A Vulnerability", security)
        self.assertIn("Manual Release Checklist", privacy)


if __name__ == "__main__":
    unittest.main()
