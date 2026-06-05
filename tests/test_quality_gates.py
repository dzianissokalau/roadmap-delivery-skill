import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"
VERSION = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
QUALITY_ROOTS = (
    REPO_ROOT / "README.md",
    REPO_ROOT / "CHANGELOG.md",
    REPO_ROOT / "VERSION",
    REPO_ROOT / "core",
    REPO_ROOT / "schemas",
    REPO_ROOT / "src",
    REPO_ROOT / "scripts",
    REPO_ROOT / "skill" / "roadmap-delivery-skill",
    REPO_ROOT / "tests",
    REPO_ROOT / "adapters",
    WORKFLOW_DIR,
)
QUALITY_SUFFIXES = {".md", ".py", ".json", ".toml", ".yml", ".yaml"}


def iter_quality_files():
    for root in QUALITY_ROOTS:
        if root.is_file():
            candidates = [root]
        elif root.exists():
            candidates = sorted(path for path in root.rglob("*") if path.is_file())
        else:
            candidates = []
        for path in candidates:
            if path.name == "VERSION" or path.suffix.lower() in QUALITY_SUFFIXES:
                yield path


class QualityGateTests(unittest.TestCase):
    maxDiff = None

    def read_workflow(self, name):
        path = WORKFLOW_DIR / name
        self.assertTrue(path.exists(), path)
        return path.read_text(encoding="utf-8")

    def test_source_quality_files_are_ascii_and_have_clean_whitespace(self):
        checked = []
        failures = []

        for path in iter_quality_files():
            checked.append(path)
            data = path.read_bytes()
            try:
                text = data.decode("ascii")
            except UnicodeDecodeError as exc:
                failures.append(f"{path.relative_to(REPO_ROOT)} has non-ASCII byte at offset {exc.start}")
                continue
            for line_number, line in enumerate(text.splitlines(keepends=True), start=1):
                body = line[:-1] if line.endswith("\n") else line
                if body.endswith((" ", "\t")):
                    failures.append(f"{path.relative_to(REPO_ROOT)}:{line_number} has trailing whitespace")
                    break
            if text and not text.endswith("\n"):
                failures.append(f"{path.relative_to(REPO_ROOT)} is missing a final newline")

        self.assertGreater(len(checked), 20)
        self.assertEqual(failures, [])

    def test_ci_workflow_runs_repository_local_quality_gates(self):
        workflow = self.read_workflow("ci.yml")

        required_snippets = (
            "name: CI",
            "python3 -m unittest discover -s tests -v",
            "python3 -m py_compile",
            "scripts/build_release.py",
            "python3 -m unittest tests.test_schema_validation -v",
            "python3 scripts/build_codex_package.py --check",
            "python3 -m unittest tests.test_quality_gates -v",
            "./.github/actions/roadmap-delivery-validate",
            "report-file: ${{ runner.temp }}/roadmap-delivery-validate.json",
            "python3 -m roadmap_delivery.cli validate",
            "git diff --check",
            "CODEX_QUICK_VALIDATE",
        )
        for snippet in required_snippets:
            with self.subTest(snippet=snippet):
                self.assertIn(snippet, workflow)

    def test_release_check_builds_local_artifact_without_publication(self):
        workflow = self.read_workflow("release-check.yml")

        required_snippets = (
            "name: Release Check",
            "'codex/**'",
            "python3 -m unittest discover -s tests -v",
            "python3 scripts/build_codex_package.py --check",
            "python3 scripts/check_release_privacy.py --repo-root .",
            "python3 scripts/build_release.py --check",
            "./.github/actions/roadmap-delivery-validate",
            "release-check: 'true'",
            "python3 scripts/build_release.py --output-dir dist --json",
            "actions/upload-artifact@v4",
            "roadmap-delivery-release-artifacts",
        )
        for snippet in required_snippets:
            with self.subTest(snippet=snippet):
                self.assertIn(snippet, workflow)
        forbidden_publication = ("gh release", "twine upload", "npm publish")
        for snippet in forbidden_publication:
            with self.subTest(snippet=snippet):
                self.assertNotIn(snippet, workflow)

    def test_workflows_do_not_require_private_codex_paths_or_credentials(self):
        for filename in ("ci.yml", "release-check.yml"):
            with self.subTest(filename=filename):
                workflow = self.read_workflow(filename)
                self.assertNotIn("/Users/", workflow)
                self.assertNotIn("~/.codex", workflow)
                self.assertNotIn("${{ secrets.", workflow)

    def test_readme_documents_local_ci_equivalents(self):
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

        required_snippets = (
            "## CI And Release Checks",
            "python3 -m unittest discover -s tests -v",
            "python3 -m py_compile",
            "python3 -m unittest tests.test_schema_validation -v",
            "python3 scripts/build_codex_package.py --check",
            "python3 -m unittest tests.test_quality_gates -v",
            "python3 scripts/build_release.py --check",
            "python3 -m roadmap_delivery.cli validate",
            "git diff --check",
            "CODEX_QUICK_VALIDATE",
            f"roadmap-delivery-{VERSION}-checksums.sha256",
        )
        for snippet in required_snippets:
            with self.subTest(snippet=snippet):
                self.assertIn(snippet, readme)


if __name__ == "__main__":
    unittest.main()
