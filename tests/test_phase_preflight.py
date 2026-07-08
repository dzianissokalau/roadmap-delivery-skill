import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "skill" / "roadmap-delivery-skill" / "scripts" / "plan_phase_prerequisites.py"
BUILD_SCRIPT = REPO_ROOT / "scripts" / "build_adapters.py"


class PhasePreflightTests(unittest.TestCase):
    maxDiff = None

    def setUp(self):
        proc = subprocess.run(
            [
                sys.executable,
                str(BUILD_SCRIPT),
                "--repo-root",
                str(REPO_ROOT),
                "--adapter",
                "codex",
                "--write",
                "--json",
            ],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)

    def test_preflight_surfaces_future_openai_network_and_retarget_blockers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            (root / "roadmaps").mkdir()
            automation_dir = root / "automation" / "preflight"
            automation_dir.mkdir(parents=True)
            roadmap = root / "roadmaps" / "preflight_roadmap.md"
            roadmap.write_text(
                "\n".join(
                    [
                        "# Preflight Roadmap",
                        "",
                        "Status: In Progress",
                        "Current Phase: Phase 1 - Prep",
                        "",
                        "## Phase 1 - Prep",
                        "",
                        "Offline setup only.",
                        "",
                        "## Phase 4 - Full Extraction Runner",
                        "",
                        "Run the full extraction runner against the OpenAI API.",
                        "",
                        "Required verification:",
                        "- `python3 scripts/full_extract.py`",
                        "",
                        "Acceptance Criteria:",
                        "- Requires OPENAI_API_KEY.",
                        "- Network access must be available.",
                    ]
                ),
                encoding="utf-8",
            )
            (automation_dir / "delivery_state.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "roadmap": "roadmaps/preflight_roadmap.md",
                        "roadmap_slug": "preflight",
                        "current_phase": "Phase 1 - Prep",
                        "status": "not_started",
                        "configured_automation_model": "gpt-5.5",
                        "configured_automation_reasoning_effort": "high",
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            (automation_dir / "phase_model_policy.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "max_stalled_runs": 2,
                        "notification": {"mode": "alert_file", "fallback": "alert_file"},
                        "defaults": {"model": "gpt-5.5", "reasoning_effort": "high"},
                        "phases": {
                            "4": {"model": "gpt-5.5", "reasoning_effort": "xhigh"},
                            "finalization": {"model": "gpt-5.5", "reasoning_effort": "xhigh"},
                        },
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            automation_config = Path(tmp) / "automation.toml"
            automation_config.write_text(
                "\n".join(
                    [
                        'model = "gpt-5.5"',
                        'reasoning_effort = "high"',
                        'status = "ACTIVE"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            env = os.environ.copy()
            env.pop("OPENAI_API_KEY", None)
            env["CODEX_SANDBOX_NETWORK_DISABLED"] = "1"
            proc = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--repo-root",
                    str(root),
                    "--roadmap-slug",
                    "preflight",
                    "--automation-config",
                    str(automation_config),
                    "--json",
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                check=False,
            )

        self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)
        report = json.loads(proc.stdout)
        self.assertEqual(report["status"], "needs_operator_setup")
        phase4 = next(phase for phase in report["phases"] if phase["phase_number"] == 4)
        codes = {issue["code"] for issue in phase4["issues"]}

        self.assertIn("missing_environment_variable", codes)
        self.assertIn("network_disabled", codes)
        self.assertIn("runner_retarget_needed", codes)
        self.assertTrue(any(issue.get("name") == "OPENAI_API_KEY" for issue in phase4["issues"]))
        self.assertTrue(any(issue.get("operation") == "retarget_saved_automation" for issue in phase4["issues"]))
        self.assertFalse(report["approval_policy"]["present"])
        self.assertTrue(
            any("OPENAI_API_KEY" in action["action"] for action in report["operator_actions"]),
            report["operator_actions"],
        )
        self.assertTrue(
            any(action.get("operation") == "retarget_saved_automation" for action in report["operator_actions"]),
            report["operator_actions"],
        )

    def test_preflight_handles_negated_network_and_present_credentials_without_secret_leak(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            (root / "roadmaps").mkdir()
            automation_dir = root / "automation" / "credential_fixture"
            automation_dir.mkdir(parents=True)
            roadmap = root / "roadmaps" / "credential_fixture_roadmap.md"
            roadmap.write_text(
                "\n".join(
                    [
                        "# Credential Fixture Roadmap",
                        "",
                        "Status: In Progress",
                        "Current Phase: Phase 1 - Offline Prep",
                        "",
                        "## Phase 1 - Offline Prep",
                        "",
                        "No network needed.",
                        "",
                        "## Phase 2 - Token Verification",
                        "",
                        "Requires DEMO_SERVICE_TOKEN.",
                        "No network needed.",
                        "",
                        "## Finalization",
                        "",
                        "Confirm completion evidence.",
                    ]
                ),
                encoding="utf-8",
            )
            (automation_dir / "delivery_state.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "roadmap": "roadmaps/credential_fixture_roadmap.md",
                        "roadmap_slug": "credential-fixture",
                        "current_phase": "Phase 1 - Offline Prep",
                        "status": "not_started",
                        "configured_automation_model": "gpt-5.5",
                        "configured_automation_reasoning_effort": "xhigh",
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            (automation_dir / "approval_policy.json").write_text(
                json.dumps(
                    {
                        "approval_mode": "conservative",
                        "operations": {
                            "edit_phase_owned_files": True,
                            "write_state_log_review_artifacts": True,
                            "create_or_switch_phase_branch": True,
                            "run_verification": True,
                            "commit_delivered_phase_locally": False,
                            "retarget_saved_automation": False,
                            "pause_saved_automation": False,
                            "push_current_phase_branch": False,
                        },
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            (automation_dir / "phase_model_policy.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "max_stalled_runs": 2,
                        "notification": {"mode": "alert_file", "fallback": "alert_file"},
                        "defaults": {"model": "gpt-5.5", "reasoning_effort": "xhigh"},
                        "phases": {
                            "finalization": {"model": "gpt-5.5", "reasoning_effort": "xhigh"},
                        },
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            output_json = root / "automation" / "credential_fixture" / "phase_prerequisites.json"
            output_md = root / "automation" / "credential_fixture" / "phase_preflight.md"
            env = os.environ.copy()
            env["DEMO_SERVICE_TOKEN"] = "leak-me-if-you-can-98765"
            env["CODEX_SANDBOX_NETWORK_DISABLED"] = "1"
            proc = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--repo-root",
                    str(root),
                    "--roadmap-slug",
                    "credential-fixture",
                    "--output-json",
                    str(output_json),
                    "--output-markdown",
                    str(output_md),
                    "--json",
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                check=False,
            )

            self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)
            report = json.loads(proc.stdout)
            combined_output = proc.stdout + output_json.read_text(encoding="utf-8") + output_md.read_text(encoding="utf-8")

        self.assertNotIn("leak-me-if-you-can-98765", combined_output)
        phase1 = next(phase for phase in report["phases"] if phase["phase_number"] == 1)
        phase2 = next(phase for phase in report["phases"] if phase["phase_number"] == 2)
        finalization = next(phase for phase in report["phases"] if phase["key"] == "finalization")

        self.assertFalse(phase1["network_required"])
        self.assertNotIn("network_disabled", {issue["code"] for issue in phase1["issues"]})
        self.assertEqual(phase2["readiness"], "needs_approval")
        self.assertFalse(phase2["network_required"])
        self.assertIn("credential_approval_required", {issue["code"] for issue in phase2["issues"]})
        self.assertNotIn(
            ("forbidden_operation", "use_credentials"),
            {(issue["code"], issue.get("operation")) for issue in phase2["issues"]},
        )
        issue_keys = [
            (issue["code"], issue.get("operation"), issue.get("name"), issue.get("tool"))
            for issue in phase2["issues"]
        ]
        self.assertEqual(len(issue_keys), len(set(issue_keys)))
        self.assertTrue(
            any(approval["operation"] == "use_credentials" and approval["decision"] == "ask" for approval in phase2["approvals"]),
            phase2["approvals"],
        )
        pause_approvals = [
            approval for approval in finalization["approvals"] if approval["operation"] == "pause_saved_automation"
        ]
        self.assertEqual(len(pause_approvals), 1)
        self.assertEqual(pause_approvals[0]["decision"], "allowed")
        self.assertEqual(pause_approvals[0]["source"], "pause_automation_on_completion")
        self.assertNotIn(
            ("approval_required", "pause_saved_automation"),
            {(issue["code"], issue.get("operation")) for issue in finalization["issues"]},
        )
        self.assertTrue(report["caveats"])

    def test_preflight_flags_network_commands_beyond_curl_and_push(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            (root / "roadmaps").mkdir()
            automation_dir = root / "automation" / "network_fixture"
            automation_dir.mkdir(parents=True)
            (root / "roadmaps" / "network_fixture_roadmap.md").write_text(
                "\n".join(
                    [
                        "# Network Fixture Roadmap",
                        "",
                        "## Phase 1 - Fetch Dependency",
                        "",
                        "Required verification:",
                        "- `git clone https://example.com/demo.git /tmp/demo`",
                    ]
                ),
                encoding="utf-8",
            )
            (automation_dir / "delivery_state.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "roadmap": "roadmaps/network_fixture_roadmap.md",
                        "roadmap_slug": "network-fixture",
                        "current_phase": "Phase 1 - Fetch Dependency",
                        "status": "not_started",
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            env = os.environ.copy()
            env["CODEX_SANDBOX_NETWORK_DISABLED"] = "1"
            proc = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--repo-root",
                    str(root),
                    "--roadmap-slug",
                    "network-fixture",
                    "--json",
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                check=False,
            )

        self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)
        report = json.loads(proc.stdout)
        phase1 = report["phases"][0]

        self.assertTrue(phase1["network_required"])
        self.assertIn("network_disabled", {issue["code"] for issue in phase1["issues"]})


if __name__ == "__main__":
    unittest.main()
