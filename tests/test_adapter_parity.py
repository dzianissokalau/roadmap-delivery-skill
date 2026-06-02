import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BUILD_SCRIPT = REPO_ROOT / "scripts" / "build_adapters.py"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
CORE_PROMPTS = REPO_ROOT / "core" / "prompts"
SNAPSHOTS = {
    "codex": REPO_ROOT / "tests" / "snapshots" / "codex" / "package_snapshot.json",
    "claude": REPO_ROOT / "tests" / "snapshots" / "claude" / "package_snapshot.json",
}
CAPABILITIES = {
    "codex": REPO_ROOT / "host-capabilities" / "codex.yaml",
    "claude": REPO_ROOT / "host-capabilities" / "claude.yaml",
}

SNAPSHOT_KEYS = {"path", "sha256", "size", "mode", "core_source", "core_sha256", "core_size"}

PARITY_RULES = {
    "one phase at a time": (
        "exactly one roadmap phase",
        "current phase",
    ),
    "blocked remediation before retry": (
        "blocked-run remediation",
        "local-repairable",
        "destructive-risk",
    ),
    "model policy boundary": (
        "phase model policy",
        "required model",
        "configured",
        "readback",
    ),
    "review verdict gate": (
        "fresh review verdict",
        "`delivered`",
        "`needs-fix`",
        "`blocked`",
    ),
    "completion hard stop": (
        "completion hard stop",
        "all phases",
        "start another phase",
    ),
    "manual activation reconciliation": (
        "manual activation",
        "last_activation",
        "active",
    ),
    "human approval for risky actions": (
        "explicit human approval",
        "destructive",
        "credentials",
    ),
    "approval policy gate": (
        "approval_policy.json",
        "`allowed`",
        "`forbidden`",
    ),
    "adaptive next-run model policy": (
        "adaptive_model_policy",
        "run quality",
        "next run",
    ),
    "completion and stall self-pause": (
        "pause_automation_on_completion",
        "pause_automation_on_stall",
        "completed_pending_pause",
    ),
}

CORE_PROMPT_COVERAGE = {
    "adaptive_model_gate.md": ("adaptive_model_policy", "run quality", "human-gated"),
    "approval_policy_gate.md": ("approval_policy.json", "`allowed`", "`forbidden`"),
    "blocked_remediation.md": ("local-repairable", "automation-config", "destructive-risk"),
    "model_policy_gate.md": ("phase model policy", "required model", "configured"),
    "review_gate.md": ("fresh review verdict", "`delivered`", "`needs-fix`"),
    "completion_hard_stop.md": ("completed_pending_pause", "all phases"),
}


class AdapterParityTests(unittest.TestCase):
    maxDiff = None
    _build_report = None

    @classmethod
    def build_report(cls):
        if cls._build_report is None:
            proc = subprocess.run(
                [
                    sys.executable,
                    str(BUILD_SCRIPT),
                    "--repo-root",
                    str(REPO_ROOT),
                    "--check",
                    "--json",
                ],
                cwd=REPO_ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            cls._build_report = cls._parse_report(proc)
            cls._build_report["_returncode"] = proc.returncode
            cls._build_report["_stderr"] = proc.stderr
        return cls._build_report

    @staticmethod
    def _parse_report(proc):
        try:
            return json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise AssertionError(proc.stderr or proc.stdout) from exc

    def report_for(self, adapter):
        return next(item for item in self.build_report()["reports"] if item["adapter"] == adapter)

    def package_corpus(self, adapter):
        report = self.report_for(adapter)
        root = Path(report["output_dir"])
        parts = []
        for item in report["files"]:
            path = root / item["path"]
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            parts.append(f"\n\n--- {adapter}:{item['path']} ---\n{text}")
        return "\n".join(parts).lower()

    def test_adapter_check_reports_clean_committed_outputs(self):
        report = self.build_report()

        self.assertEqual(report["_returncode"], 0, report["_stderr"] or json.dumps(report, indent=2))
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["adapters"], ["codex", "claude"])
        for adapter_report in report["reports"]:
            with self.subTest(adapter=adapter_report["adapter"]):
                self.assertEqual(adapter_report["status"], "ok", adapter_report)
                self.assertEqual(adapter_report["diffs"], [], adapter_report)
                self.assertEqual(adapter_report["errors"], [], adapter_report)
                self.assertEqual(adapter_report["check_mode"], "output")
                self.assertTrue(adapter_report["output_committed"])

    def test_marketplace_readiness_report_covers_supported_package_evidence(self):
        for adapter_report in self.build_report()["reports"]:
            with self.subTest(adapter=adapter_report["adapter"]):
                readiness = adapter_report["marketplace_readiness"]
                self.assertEqual(readiness["status"], "ok", readiness)
                self.assertEqual(readiness["failures"], [])
                check_names = {item["name"] for item in readiness["checks"]}

                self.assertIn("host capability metadata", check_names)
                self.assertTrue(any(name.startswith("package file ") for name in check_names))
                self.assertTrue(any("readiness documentation docs/installing-" in name for name in check_names))
                self.assertIn("readiness documentation docs/adapters.md", check_names)
                self.assertIn("readiness documentation docs/compatibility.md", check_names)

    def test_generated_package_snapshots_match_adapter_reports(self):
        for adapter, snapshot_path in SNAPSHOTS.items():
            with self.subTest(adapter=adapter):
                snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
                actual = [
                    {key: value for key, value in item.items() if key in SNAPSHOT_KEYS}
                    for item in self.report_for(adapter)["files"]
                ]

                self.assertEqual(snapshot["schema_version"], 1)
                self.assertEqual(snapshot["adapter"], adapter)
                self.assertEqual(snapshot["files"], actual)

    def test_required_core_workflow_rules_are_present_in_each_adapter_package(self):
        for adapter in ("codex", "claude"):
            corpus = self.package_corpus(adapter)
            for rule, terms in PARITY_RULES.items():
                for term in terms:
                    with self.subTest(adapter=adapter, rule=rule, term=term):
                        self.assertIn(term.lower(), corpus)

    def test_core_prompt_fragments_are_represented_in_generated_packages(self):
        prompt_names = {path.name for path in CORE_PROMPTS.glob("*.md")}
        self.assertEqual(set(CORE_PROMPT_COVERAGE), prompt_names)

        for adapter in ("codex", "claude"):
            corpus = self.package_corpus(adapter)
            for prompt_name, terms in CORE_PROMPT_COVERAGE.items():
                for term in terms:
                    with self.subTest(adapter=adapter, prompt=prompt_name, term=term):
                        self.assertIn(term.lower(), corpus)

    def test_adapter_drift_report_identifies_the_failing_adapter(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_proc = subprocess.run(
                [
                    sys.executable,
                    str(BUILD_SCRIPT),
                    "--repo-root",
                    str(REPO_ROOT),
                    "--write",
                    "--output-root",
                    tmp,
                    "--json",
                ],
                cwd=REPO_ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(write_proc.returncode, 0, write_proc.stderr or write_proc.stdout)

            stale_file = Path(tmp) / "codex" / "SKILL.md"
            stale_file.write_text("stale codex package\n", encoding="utf-8")

            check_proc = subprocess.run(
                [
                    sys.executable,
                    str(BUILD_SCRIPT),
                    "--repo-root",
                    str(REPO_ROOT),
                    "--check",
                    "--output-root",
                    tmp,
                    "--json",
                ],
                cwd=REPO_ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

        report = self._parse_report(check_proc)
        by_adapter = {item["adapter"]: item for item in report["reports"]}

        self.assertEqual(check_proc.returncode, 1, check_proc.stderr or check_proc.stdout)
        self.assertEqual(report["status"], "drift")
        self.assertEqual(by_adapter["codex"]["status"], "drift")
        self.assertEqual(by_adapter["codex"]["diffs"][0]["path"], "SKILL.md")
        self.assertEqual(by_adapter["claude"]["status"], "ok")
        self.assertEqual(by_adapter["claude"]["diffs"], [])

    def test_host_specific_differences_are_documented_with_fallbacks(self):
        for adapter, path in CAPABILITIES.items():
            lines = path.read_text(encoding="utf-8").splitlines()
            for index, line in enumerate(lines):
                if "parity_level: host_specific_enhancement" not in line and "parity_level: unsupported_by_host" not in line:
                    continue
                context = "\n".join(lines[index : index + 8])
                with self.subTest(adapter=adapter, line=index + 1):
                    self.assertIn("fallback:", context)

    def test_ci_discovers_parity_tests(self):
        workflow = CI_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("python3 -m unittest discover -s tests -v", workflow)


if __name__ == "__main__":
    unittest.main()
