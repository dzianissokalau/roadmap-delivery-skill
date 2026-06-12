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


if __name__ == "__main__":
    unittest.main()
