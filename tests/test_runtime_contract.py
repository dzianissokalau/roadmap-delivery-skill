"""Phase 0 fixture checks and opt-in isolated baseline capture.

The default suite checks the evidence contract, never the defective runtime as
an oracle. Owning phases add behavioral assertions against expected_result.
"""

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "runtime-reliability"
CONTRACT_PATH = REPO_ROOT / "docs" / "runtime-control-contract.md"
STAGES = (
    "terminal_reconciliation",
    "intentional_activation",
    "blocked_remediation",
    "phase_prerequisites",
    "delivery_review",
    "next_phase_or_finalization",
)
CASE_IDS = {"R1", "R2", "R3", "R4", "R5", "R6"}
EVENTS = {"start_run", "record_outcome", "recover_run", "operator_resume", "phase_review", "advance_phase"}


def load_fixture(name):
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))


def validate_cases(document):
    """Validate the Phase 0 evidence format without making runtime decisions."""
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        raise ValueError("Expected versioned fixture object")
    if document.get("contract") != "docs/runtime-control-contract.md":
        raise ValueError("Expected canonical contract reference")
    cases = document.get("cases")
    if not isinstance(cases, list) or len(cases) != len(CASE_IDS):
        raise ValueError("Expected all six findings")
    ids = [case.get("id") for case in cases if isinstance(case, dict)]
    if len(ids) != len(cases) or set(ids) != CASE_IDS:
        raise ValueError("Finding IDs must be unique and complete")
    for case in cases:
        for field in ("title", "reproduction_command"):
            if not isinstance(case.get(field), str) or not case[field].strip():
                raise ValueError("Missing " + field)
        for field in ("input", "expected_result"):
            if not isinstance(case.get(field), dict) or not case[field]:
                raise ValueError("Missing explicit " + field)
        if "observed_result" in case:
            raise ValueError("Baseline observations must stay separate from oracles")
        if case.get("evidence_type") not in {"executable", "instruction_provenance"}:
            raise ValueError("Unknown evidence type")
        if (case["id"] == "R3") != (case["evidence_type"] == "instruction_provenance"):
            raise ValueError("R3 is instruction evidence, not a live reproduction")
        if not isinstance(case.get("fix_phases"), list) or not case["fix_phases"]:
            raise ValueError("Missing regression owner")
        if any(type(phase) is not int or not 1 <= phase <= 8 for phase in case["fix_phases"]):
            raise ValueError("Invalid regression owner")
        if not isinstance(case.get("sources"), list) or not case["sources"]:
            raise ValueError("Missing source evidence")
        for source in case["sources"]:
            if not isinstance(source, str):
                raise ValueError("Source must be a repository path")
            path = Path(source)
            if path.is_absolute() or ".." in path.parts or not (REPO_ROOT / path).is_file():
                raise ValueError("Source must exist inside the repository")
    return cases


def capture_case(case, root):
    """Invoke current sources with fixture-only state/configuration."""
    from roadmap_delivery.adaptive import resolve_adaptive_action
    from roadmap_delivery.approval import approval_decision_for_pause_context, default_approval_policy
    from roadmap_delivery.automation import pause_saved_automation
    from roadmap_delivery.progress import build_run_result
    from roadmap_delivery.validation import validate_model_policy

    raw = case["input"]
    if case["id"] == "R1":
        repo = root / "repo"
        directory = repo / "automation" / "fixture"
        directory.mkdir(parents=True)
        state_file = directory / "delivery_state.json"
        state = copy.deepcopy(raw["state"])
        (directory / "phase_model_policy.json").write_text(
            json.dumps({"max_stalled_runs": raw["max_stalled_runs"]}), encoding="utf-8"
        )
        observations = []
        for number, run_id in enumerate(raw["run_ids"], 1):
            (directory / "delivery_log.md").write_text(
                raw["log_template"].format(run=number), encoding="utf-8"
            )
            result = build_run_result(repo, state_file, state, timestamp="fixture-time")
            observations.append({"run_id": run_id, **{
                key: result[key] for key in (
                    "run_count", "stalled_run_count", "threshold_reached", "progress_detected",
                    "progress_signature", "previous_progress_signature",
                )
            }})
            state.update(run_count=result["run_count"], stalled_run_count=result["stalled_run_count"],
                         last_progress_signature=result["progress_signature"])
        return {"runs": observations, "method": "pure planning only; no host effects"}
    if case["id"] == "R2":
        installed = root / "install" / "skills" / "roadmap-delivery-skill"
        shutil.copytree(REPO_ROOT / raw["package"], installed)
        other_repo = root / "other-repository"
        other_repo.mkdir()
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        outputs = []
        for helper in raw["helpers"]:
            command = [sys.executable, *raw["python_flags"], str(installed / "scripts" / helper),
                       *raw["arguments"]]
            proc = subprocess.run(command, cwd=other_repo, env=env, text=True,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
            outputs.append({"helper": helper, "command": ["python3", *raw["python_flags"],
                            "<isolated-install>/scripts/" + helper, *raw["arguments"]],
                            "returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr})
        return {"helpers": outputs, "checkout_on_child_import_path": False,
                "site_packages_enabled": False}
    if case["id"] == "R3":
        config = root / "legacy-automation.toml"
        config.write_text('status = "ACTIVE"\nprompt = ' + json.dumps(raw["legacy_prompt"]) + "\n",
                          encoding="utf-8")
        before = hashlib.sha256(config.read_bytes()).hexdigest()
        shutil.copytree(REPO_ROOT / "skill" / "roadmap-delivery-skill", root / "installed-skill")
        evidence = []
        excerpts = (
            (case["sources"][0], "If a context-specific pause flag is absent", 4),
            (case["sources"][1], "- Pausing, publication", 2),
        )
        for source, needle, length in excerpts:
            lines = (REPO_ROOT / source).read_text(encoding="utf-8").splitlines()
            index = next(i for i, line in enumerate(lines) if needle in line)
            evidence.append({"source": source, "line": index + 1,
                             "text": "\n".join(lines[index:index + length])})
        return {"source_excerpts": evidence, "saved_config_before_sha256": before,
                "saved_config_after_sha256": hashlib.sha256(config.read_bytes()).hexdigest(),
                "saved_prompt_after_package_copy": raw["legacy_prompt"],
                "live_scheduler_verified": False, "host_update_attempted": False,
                "provenance": "sanitized scenario; not a captured live legacy runner"}
    if case["id"] == "R4":
        automation_root = root / "fixture-automations"
        config = automation_root / raw["automation_id"] / "automation.toml"
        config.parent.mkdir(parents=True)
        config.write_text(raw["config_text"], encoding="utf-8")
        try:
            result = pause_saved_automation(raw["automation_id"], root=automation_root,
                                            timestamp="fixture-time", reason="isolated reproduction")
            result.pop("config_path", None)
        except Exception as exc:  # strict parsers can reject the malformed candidate
            result = {"exception_type": type(exc).__name__, "message": str(exc)}
        candidate = config.read_text(encoding="utf-8")
        return {"candidate_text": candidate,
                "status_assignment_count": len(re.findall(r"(?m)^status\s*=", candidate)),
                "helper_result": result, "scheduler_pause_verified": False}
    if case["id"] == "R5":
        observations = []
        for mode in raw["modes"]:
            policy = default_approval_policy(mode, pause_on_completion=False, pause_on_stall=False)
            for context in raw["contexts"]:
                observations.append({"mode": mode, "context": context, "raw_policy": policy,
                                     "decision": approval_decision_for_pause_context(policy, context)})
        return {"decisions": observations, "host_update_attempted": False}
    if case["id"] == "R6":
        policy_file = root / "phase_model_policy.json"
        policy_file.write_text(json.dumps(raw["policy"]), encoding="utf-8")
        errors, warnings = [], []
        policy_report = validate_model_policy(
            policy_file, {"current_phase": "Phase 1 - Fixture"},
            {"model": raw["base_model"], "reasoning_effort": raw["base_reasoning_effort"]},
            errors, warnings, load_json(REPO_ROOT / "schemas" / "phase_model_policy.schema.json"),
        )
        action = resolve_adaptive_action(raw["policy"], **{
            key: raw[key] for key in ("base_model", "base_reasoning_effort", "run_quality", "flawless_streak")
        })
        return {"policy_errors": errors, "policy_warnings": warnings,
                "validated_phase_reasoning": policy_report["required_reasoning_effort"],
                "adaptive_action": action, "host_update_attempted": False}
    raise ValueError("Unrecognized finding")


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def capture_baseline(output):
    # Parent-side checkout imports are deliberate baseline access. R2 children
    # run -I -S outside the checkout and cannot inherit this sys.path.
    sys.path.insert(0, str(REPO_ROOT / "src"))
    cases = validate_cases(load_fixture("cases.json"))
    report = {
        "schema_version": 1,
        "base_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT,
                                               text=True).strip(),
        "captured_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "python_version": sys.version.split()[0],
        "scope": "offline isolated baseline, no live scheduler mutation or verification",
        "cases": [],
    }
    with tempfile.TemporaryDirectory(prefix="roadmap-contract-") as tmp:
        for case in cases:
            root = Path(tmp) / case["id"]
            root.mkdir()
            report["cases"].append({
                **case, "observed_result": capture_case(case, root), "capture_status": "observed",
            })
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("Captured R1-R6 baseline to " + str(output))


class RuntimeContractTests(unittest.TestCase):
    def test_six_cases_have_traceable_inputs_expected_results_and_regression_owners(self):
        validate_cases(load_fixture("cases.json"))

    def test_malformed_evidence_is_rejected(self):
        base = load_fixture("cases.json")
        variants = []
        for field in ("input", "expected_result", "sources", "fix_phases", "reproduction_command"):
            bad = copy.deepcopy(base)
            bad["cases"][0].pop(field)
            variants.append(bad)
        for value in ("live_scheduler", "unknown"):
            bad = copy.deepcopy(base)
            bad["cases"][2]["evidence_type"] = value
            variants.append(bad)
        bad = copy.deepcopy(base)
        bad["cases"][0]["observed_result"] = {"broken": True}
        variants.append(bad)
        bad = copy.deepcopy(base)
        bad["cases"][1]["id"] = "R1"
        variants.append(bad)
        bad = copy.deepcopy(base)
        bad["cases"][0]["sources"] = ["../outside-repo.py"]
        variants.append(bad)
        for index, document in enumerate(variants):
            with self.subTest(index=index), self.assertRaises(ValueError):
                validate_cases(document)

    def test_baseline_report_is_observation_evidence_with_matching_oracles(self):
        cases = validate_cases(load_fixture("cases.json"))
        report = load_fixture("baseline-report.json")
        self.assertEqual(report["schema_version"], 1)
        self.assertRegex(report["base_commit"], r"^[0-9a-f]{40}$")
        self.assertTrue(report["captured_at"])
        self.assertIn("no live scheduler", report["scope"])
        self.assertEqual([case["id"] for case in report["cases"]], [case["id"] for case in cases])
        for oracle, observation in zip(cases, report["cases"]):
            with self.subTest(finding=oracle["id"]):
                for key, value in oracle.items():
                    self.assertEqual(observation[key], value)
                self.assertEqual(observation["capture_status"], "observed")
                self.assertIsInstance(observation["observed_result"], dict)
                self.assertTrue(observation["observed_result"])

    def test_transition_matrix_has_ordered_stage_and_observable_result_contract(self):
        matrix = load_fixture("transition-matrix.json")
        self.assertEqual(matrix["schema_version"], 1)
        self.assertEqual(matrix["ordered_stages"], list(STAGES))
        self.assertEqual(set(matrix["events"]), EVENTS)
        ids = set()
        stages = set()
        events = set()
        for scenario in matrix["scenarios"]:
            with self.subTest(scenario=scenario["id"]):
                self.assertNotIn(scenario["id"], ids)
                ids.add(scenario["id"])
                self.assertIn(scenario["expected_stage"], STAGES)
                stages.add(scenario["expected_stage"])
                self.assertIn(scenario["event"], EVENTS)
                events.add(scenario["event"])
                self.assertTrue(scenario["input"])
                self.assertTrue(scenario["expected_action"])
                self.assertTrue(scenario["expected_result"])
        self.assertEqual(stages, set(STAGES))
        self.assertEqual(events, EVENTS)
        self.assertTrue({"terminal-before-model", "terminal-before-activation", "first-no-progress",
                         "second-no-progress", "duplicate-outcome", "restart-interrupted",
                         "resume-no-repair", "resume-explicit-budget", "last-numbered-phase"} <= ids)

    def test_contract_defines_required_distinctions_and_links_to_fixture_evidence(self):
        text = CONTRACT_PATH.read_text(encoding="utf-8")
        for stage in STAGES:
            self.assertIn(stage, text)
        for event in EVENTS:
            self.assertIn(event, text)
        for concept in ("Unique Runs And Recovery", "Semantic Progress Evidence",
                        "Authority And Policy Precedence", "Runner Identity, Readback And Effects",
                        "Completion And Stall Outcomes", "First no-progress attempt",
                        "Second unique no-progress attempt", "Duplicate invocation/outcome",
                        "Restart with unfinished start", "Operator resumes scheduler",
                        "cases.json", "baseline-report.json", "transition-matrix.json"):
            with self.subTest(concept=concept):
                self.assertIn(concept, text)


if __name__ == "__main__":
    if "--capture-baseline" in sys.argv:
        parser = argparse.ArgumentParser(description="Capture current defects without asserting them as oracles")
        parser.add_argument("--capture-baseline", action="store_true")
        parser.add_argument("--output", type=Path, required=True)
        arguments = parser.parse_args()
        capture_baseline(arguments.output)
    else:
        unittest.main()
