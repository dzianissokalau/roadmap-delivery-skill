import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from roadmap_delivery.paths import extract_roadmap_references, resolve_repo_path, slug_forms, state_candidates
from roadmap_delivery.policy import has_blocked_remediation_guard, has_hard_stop_guard, normalized, phase_number
from roadmap_delivery.progress import build_run_result
from roadmap_delivery.state import load_json_object
from roadmap_delivery.toml import parse_minimal_toml
from roadmap_delivery.validation import validate_json_schema


class LibraryUnitTests(unittest.TestCase):
    def test_slug_and_state_candidates_support_dash_and_directory_forms(self):
        repo_root = Path("/repo")
        forms = slug_forms("framework-core")

        self.assertEqual(forms["dash"], "framework-core")
        self.assertEqual(forms["dir"], "framework_core")
        self.assertEqual(
            state_candidates(repo_root, forms),
            [
                repo_root / "roadmaps" / "automation" / "framework_core" / "delivery_state.json",
                repo_root / "automation" / "framework_core" / "delivery_state.json",
                repo_root / "roadmaps" / "automation" / "framework-core" / "delivery_state.json",
                repo_root / "automation" / "framework-core" / "delivery_state.json",
            ],
        )

    def test_roadmap_references_normalize_relative_prompt_paths(self):
        repo_root = Path("/repo")
        prompt = (
            "Run `roadmaps/in_progress_framework_core_roadmap.md` and ignore "
            "`notes/plain.md`."
        )

        refs = extract_roadmap_references(prompt, repo_root, require_roadmap_suffix=True)

        self.assertEqual(refs, [repo_root / "roadmaps" / "in_progress_framework_core_roadmap.md"])

    def test_minimal_toml_parser_handles_codex_automation_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "automation.toml"
            path.write_text(
                "\n".join(
                    [
                        'id = "framework-core"',
                        'status = "ACTIVE"',
                        'cwds = ["/repo"]',
                        "version = 1",
                        "enabled = true",
                    ]
                ),
                encoding="utf-8",
            )

            parsed = parse_minimal_toml(path)

        self.assertEqual(parsed["id"], "framework-core")
        self.assertEqual(parsed["cwds"], ["/repo"])
        self.assertEqual(parsed["version"], 1)
        self.assertTrue(parsed["enabled"])

    def test_policy_helpers_match_automation_prompt_guards(self):
        prompt = (
            "If state is completed_pending_pause or all_phases_complete, do not start. "
            "If status is blocked, enter Blocked Remediation Mode, repair local blockers "
            "before advance, and only then resume."
        )

        self.assertTrue(has_hard_stop_guard(prompt))
        self.assertTrue(has_blocked_remediation_guard(prompt))
        self.assertEqual(normalized("Completed_Pending_Pause"), "completed-pending-pause")
        self.assertEqual(phase_number("Phase 12 - Closeout"), "12")

    def test_schema_validator_and_state_loader_are_importable_library_units(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            path.write_text('{"schema_version": 1}', encoding="utf-8")

            state = load_json_object(path)
            errors = validate_json_schema(state, {"type": "object", "required": ["schema_version"]})

        self.assertEqual(state["schema_version"], 1)
        self.assertEqual(errors, [])

    def test_progress_result_uses_shared_state_shape_without_recording(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            state_dir = repo_root / "automation" / "fixture"
            state_dir.mkdir(parents=True)
            state_file = state_dir / "delivery_state.json"
            state = {
                "current_phase": "Phase 1 - Fixture",
                "status": "not_started",
                "last_delivered_phase": None,
                "review_iterations": 0,
                "last_verification": None,
                "last_review": None,
                "blocked_reason": None,
            }
            state_file.write_text(json.dumps(state), encoding="utf-8")
            (state_dir / "delivery_log.md").write_text("# Log\n", encoding="utf-8")

            result = build_run_result(repo_root, state_file, state, timestamp="2026-05-25T00:00:00Z")

        self.assertFalse(result["progress_detected"])
        self.assertTrue(result["outcome_pending"])
        self.assertEqual(result["run_count"], 0)

    def test_resolve_repo_path_preserves_absolute_paths(self):
        repo_root = Path("/repo")

        self.assertEqual(resolve_repo_path(repo_root, "roadmaps/example.md"), repo_root / "roadmaps" / "example.md")
        self.assertEqual(resolve_repo_path(repo_root, "/tmp/example.md"), Path("/tmp/example.md"))


if __name__ == "__main__":
    unittest.main()
