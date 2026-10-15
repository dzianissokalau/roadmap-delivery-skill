"""Equivalent offline inputs across source CLI and independently copied host packages."""
import ast
import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from roadmap_delivery.approval import default_approval_policy
from roadmap_delivery import reports, validation
from roadmap_delivery.migrations import LEGACY_PROMPTS, VERSIONS, plan_migration, render_prompt
from roadmap_delivery.automation import runner_snapshot
from roadmap_delivery.policy import has_blocked_remediation_guard, has_hard_stop_guard, has_state_resolved_roadmap_guard
from roadmap_delivery.scaffold import ScaffoldOptions, build_scaffold_plan
from roadmap_delivery.wizard import WizardOptions, build_wizard_plan

ROOT = Path(__file__).resolve().parents[1]
SEMANTIC_KEYS = ("stage", "action", "result", "reason_code", "authority", "proposed_state_changes",
                 "required_effects", "extract_phase", "completion_claim", "exit_code")


def semantic(plan):
    return {key: plan.get(key) for key in SEMANTIC_KEYS}


class RuntimeEntrypointTests(unittest.TestCase):
    def setUp(self):
        self.storage = tempfile.TemporaryDirectory(prefix="runtime-entrypoints-")
        self.addCleanup(self.storage.cleanup)
        self.base = Path(self.storage.name).resolve()
        self.repo = self.base / "repo"; self.repo.mkdir()
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        self.directory = self.repo / "automation/entrypoints"; self.directory.mkdir(parents=True)
        (self.directory / "reviews").mkdir()
        (self.directory / "delivery_log.md").write_text("# Test log\n")
        (self.repo / "roadmaps").mkdir()
        (self.repo / "roadmaps/in_progress_entrypoints.md").write_text(
            "# Entrypoints\nStatus: Active\nCurrent phase: Phase 7 - Integration\n\n"
            "## Phase 7 - Integration\nOffline local work only.\n\n## Phase 8 - Acceptance\nOffline.\n")
        self.automations = self.base / "automations"; self.config_dir = self.automations / "fixture"
        self.config_dir.mkdir(parents=True)
        self.state = {"schema_version": 1, "roadmap": "roadmaps/in_progress_entrypoints.md",
            "roadmap_slug": "entrypoints", "current_phase": "Phase 7 - Integration", "status": "not_started",
            "run_count": 0, "stalled_run_count": 0, "max_stalled_runs": 2,
            "review_iterations": 0, "max_review_iterations": 3, "last_verification": None, "last_review": None,
            "configured_automation_status": "ACTIVE", "configured_execution_environment": "local",
            "automation": {"id": "fixture", "project_id": "project", "status": "ACTIVE"}}
        self.policy = {"schema_version": 1, "max_stalled_runs": 2,
            "notification": {"mode": "alert_file", "fallback": "alert_file"},
            "defaults": {"model": "fixture-model", "reasoning_effort": "high"},
            "phases": {"finalization": {"model": "fixture-model", "reasoning_effort": "high"}},
            "adaptive_model_policy": {"enabled": False}}
        self.approval = default_approval_policy("conservative")
        self.config = {"id": "fixture", "status": "ACTIVE", "model": "fixture-model", "reasoning_effort": "xhigh",
            "cwds": [str(self.repo)], "execution_environment": "local", "target": {"type": "project", "project_id": "project"},
            "prompt": render_prompt("entrypoints")}
        self.env = os.environ.copy()
        self.env.pop("PYTHONPATH", None); self.env.pop("PYTHONHOME", None)
        self.env["AUTONOMOUS_ROADMAP_AUTOMATIONS_DIR"] = str(self.automations)
        self.env["PYTHONNOUSERSITE"] = "1"
        # A source-free installed tree; -I -S excludes checkout and site packages.
        self.codex = self.base / "codex"
        shutil.copytree(ROOT / "skill/roadmap-delivery-skill", self.codex, ignore=shutil.ignore_patterns("__pycache__"))
        self.claude = self.base / "claude"
        shutil.copytree(ROOT / "dist/claude", self.claude, ignore=shutil.ignore_patterns("__pycache__"))
        self.claude_skill = self.claude / "skills/roadmap-delivery-skill"
        self.save()

    def save(self):
        (self.directory / "delivery_state.json").write_text(json.dumps(self.state))
        (self.directory / "phase_model_policy.json").write_text(json.dumps(self.policy))
        if self.approval is None:
            (self.directory / "approval_policy.json").unlink(missing_ok=True)
        else:
            (self.directory / "approval_policy.json").write_text(json.dumps(self.approval))
        # This input writer emits only known fixture fields. Real runner effects use host tooling.
        config = self.config
        (self.config_dir / "automation.toml").write_text("\n".join(
            f"{k} = {json.dumps(v)}" for k, v in config.items() if k != "target") +
            '\ntarget = { type = "project", project_id = "project" }\n')

    def common(self):
        return ["--repo-root", str(self.repo), "--roadmap-slug", "entrypoints", "--automation-id", "fixture", "--json"]

    def execute(self, skill, helper, *args):
        proc = subprocess.run([sys.executable, "-I", "-S", str(skill / "scripts" / helper), *args],
                              cwd=self.repo, env=self.env, capture_output=True, text=True)
        self.assertTrue(proc.stdout.strip(), proc.stderr)
        try:
            return json.loads(proc.stdout)
        except ValueError:
            self.fail(proc.stdout + proc.stderr)

    def canonical(self):
        with patch.object(reports, "AUTOMATIONS_DIR", self.automations), patch.object(validation, "AUTOMATIONS_DIR", self.automations):
            return reports.build_control_plan(self.repo, "entrypoints", "fixture")

    def assert_routes(self):
        expected = semantic(self.canonical())
        for skill in (self.codex, self.claude_skill):
            for helper, prefix in (
                ("roadmap_delivery.py", ["plan-control"]),
                ("roadmap_delivery.py", ["inspect"]),
                ("roadmap_delivery.py", ["validate"]),
                ("inspect_delivery_state.py", []),
                ("validate_delivery_artifacts.py", []),
                ("plan_phase_prerequisites.py", []),
                ("roadmap_delivery.py", ["phase-preflight"]),
                ("plan_automation_retarget.py", []),
                ("roadmap_delivery.py", ["plan-retarget"]),
            ):
                extra = ["--delivered-phase", "Phase 7 - Integration"] if helper == "plan_automation_retarget.py" or prefix == ["plan-retarget"] else []
                with self.subTest(skill=skill.name, helper=helper, prefix=prefix):
                    result = self.execute(skill, helper, *prefix, *self.common(), *extra)
                    plan = result if prefix == ["plan-control"] else result["control_plan"]
                    self.assertEqual(expected, semantic(plan))
        return expected

    def test_ready_and_higher_reasoning_are_equivalent(self):
        self.assertEqual(self.assert_routes()["reason_code"], "phase_prerequisites_unverified")

    def test_source_control_checks_configured_host_support_before_phase_work(self):
        metadata = {"trusted": True, "source": "offline-adapter", "models": {
            "fixture-model": {"reasoning_efforts": ["high"]}}}
        for efforts, ready in ((["high"], False), (["high", "xhigh"], True)):
            metadata["models"]["fixture-model"]["reasoning_efforts"] = efforts
            with patch.object(reports, "AUTOMATIONS_DIR", self.automations):
                result = reports.build_control_plan(self.repo, "entrypoints", "fixture",
                    host_capabilities=metadata, evidence={"prerequisites_passed": True})
            self.assertEqual(result["extract_phase"], ready)
            self.assertEqual(result["result"], "ready" if ready else "invalid_input")
            if not ready:
                self.assertIn("configured_target_host_unsupported", {e["code"] for e in result["prerequisite_errors"]})

    def test_capability_backed_planner_target_survives_destination_phase(self):
        metadata = {"trusted": True, "source": "offline-adapter", "models": {
            name: {"reasoning_efforts": ["high", "xhigh"], "provider": "fixture-vendor"}
            for name in ("fixture-model", "larger-model")}}
        metadata_file = self.base / "capabilities.json"; metadata_file.write_text(json.dumps(metadata))
        self.policy["adaptive_model_policy"] = {"enabled": True,
            "caps": {"allowed_models": ["fixture-model", "larger-model"], "max_reasoning_effort": "xhigh", "allowed_providers": ["fixture-vendor"]},
            "escalation": {"model": "larger-model", "reasoning_effort": "xhigh"}}
        self.state.update(last_completed_run_id="source-run",
            last_verification={"phase": self.state["current_phase"], "run_id": "source-run", "status": "passed"},
            last_review={"phase": self.state["current_phase"], "run_id": "source-run", "verdict": "delivered", "iteration": 2})
        self.save()
        plan = self.execute(self.codex, "plan_automation_retarget.py", *self.common(),
            "--delivered-phase", "Phase 7 - Integration", "--capabilities-file", str(metadata_file))
        self.assertEqual(plan["target"]["model"], "larger-model")
        self.state.update(plan["state_updates"])
        self.config.update(model="larger-model", reasoning_effort="xhigh")
        for stage in ("start", "verification", "review", "finish"):
            self.state["active_run"] = {"phase": self.state["current_phase"], "run_id": "destination-run"}
            if stage != "start": self.state["last_verification"] = {"phase": self.state["current_phase"], "run_id": "destination-run", "status": "passed"}
            if stage in ("review", "finish"): self.state["last_review"] = {"phase": self.state["current_phase"], "run_id": "destination-run", "verdict": "delivered"}
            if stage == "finish": self.state.update(active_run=None, last_completed_run_id="destination-run")
            self.save()
            for skill in (self.codex, self.claude_skill):
                for command in ("inspect", "validate", "plan-control"):
                    with self.subTest(stage=stage, skill=skill.name, command=command):
                        result = self.execute(skill, "roadmap_delivery.py", command, *self.common())
                        if command != "plan-control":
                            self.assertEqual(result["model_policy"]["persisted_target_status"], "resolved")
                            self.assertEqual(result["model_policy"]["required_model"], "larger-model")
                        control = result if command == "plan-control" else result["control_plan"]
                        self.assertNotIn(control["reason_code"], {"invalid_model_target", "model_mismatch", "invalid_prerequisites"})
                        self.assertEqual(control["prerequisite_errors"], [])
        metadata["models"]["larger-model"]["provider"] = "no-longer-approved"
        metadata_file.write_text(json.dumps(metadata))
        changed = self.execute(self.codex, "roadmap_delivery.py", "validate", *self.common(), "--capabilities-file", str(metadata_file))
        self.assertEqual(changed["model_policy"]["persisted_target_status"], "ignored_changed_capabilities")

    def test_installed_recovery_preserves_completion_and_counters(self):
        state_file = self.directory / "delivery_state.json"
        for skill in (self.codex, self.claude_skill):
            for marker in ({"status": "completed_pending_pause"}, {"all_phases_complete": True}):
                with self.subTest(skill=skill.name, marker=marker):
                    (self.directory / "automation_run_log.jsonl").unlink(missing_ok=True)
                    self.save()
                    self.execute(skill, "compute_progress_signature.py", *self.common(), "--start-run", "--run-id", "unfinished")
                    value = json.loads(state_file.read_text()); value.update(marker); state_file.write_text(json.dumps(value))
                    before = state_file.read_bytes()
                    proc = subprocess.run([sys.executable, "-I", "-S", str(skill / "scripts/compute_progress_signature.py"),
                        *self.common(), "--recover-run", "--run-id", "unfinished"], cwd=self.repo, env=self.env, capture_output=True, text=True)
                    self.assertEqual(proc.returncode, 1)
                    self.assertIn("Completed scope", proc.stderr)
                    self.assertEqual(before, state_file.read_bytes())
        self.config["reasoning_effort"] = "ultra"; self.save()
        self.assertEqual(self.assert_routes()["reason_code"], "phase_prerequisites_unverified")

    def test_activation_and_original_blocker_use_shared_order(self):
        self.state["configured_automation_status"] = "PAUSED"; self.save()
        self.assertEqual(self.assert_routes()["action"], "reconcile_activation")
        self.state.update(status="blocked", blocked_reason="Original missing fixture", configured_automation_status="ACTIVE")
        self.save(); self.assertEqual(self.assert_routes()["stage"], "blocked_remediation")

    def test_terminal_precedes_bad_model_and_respects_all_mode_optouts(self):
        self.state["status"] = "completed_pending_pause"; self.config["model"] = "wrong-model"
        for mode in ("conservative", "delegated_local", "delegated_delivery", "custom"):
            self.approval = default_approval_policy(mode, {"pause_saved_automation": True}, pause_on_completion=False)
            self.save(); decision = self.assert_routes()
            self.assertEqual(decision["stage"], "terminal_reconciliation")
            self.assertEqual(decision["action"], "record_disabled")
            self.assertFalse(decision["extract_phase"])
        self.approval = None; self.save()
        self.assertEqual(self.assert_routes()["authority"]["decision"], "allowed")

    def test_stall_and_invalid_policy_are_distinct_terminal_outcomes(self):
        self.state.update(status="blocked", blocked_reason="Missing input", stalled_run_count=2)
        self.save(); self.assertEqual(self.assert_routes()["reason_code"], "pause_capability_unavailable")
        self.approval = {"schema_version": 999}; self.save()
        self.assertEqual(self.assert_routes()["reason_code"], "invalid_policy")

    def test_model_constraints_and_missing_readback_cannot_use_cached_state(self):
        self.policy["adaptive_model_policy"] = {"enabled": False, "floors": {"min_reasoning_effort": "xhigh"}}
        self.config["reasoning_effort"] = "high"; self.save()
        self.assertEqual(self.assert_routes()["reason_code"], "phase_model_mismatch")
        self.state.update(configured_automation_model="fixture-model", configured_automation_reasoning_effort="ultra")
        self.config_dir.joinpath("automation.toml").unlink()
        self.directory.joinpath("delivery_state.json").write_text(json.dumps(self.state))
        self.assertEqual(self.assert_routes()["reason_code"], "phase_model_mismatch")

    def test_setup_proposals_have_same_decision_and_no_invented_runner(self):
        options = ScaffoldOptions(repo_root=self.repo, roadmap_slug="new-fixture", initial_model="fixture-model", reasoning_effort="high")
        scaffold = build_scaffold_plan(options); wizard = build_wizard_plan(WizardOptions(options))
        self.assertEqual(semantic(scaffold["control_plan"]), semantic(wizard["control_plan"]))
        self.assertEqual(scaffold["control_plan"]["reason_code"], "phase_model_mismatch")
        self.assertFalse(scaffold["control_plan"]["extract_phase"])
        self.assertFalse(wizard["live_automation"]["edited"])

    def test_current_prompt_guards_and_exact_preceding_upgrade_are_preserved(self):
        prompt = render_prompt("entrypoints")
        self.assertTrue(has_blocked_remediation_guard(prompt))
        self.assertTrue(has_hard_stop_guard(prompt))
        self.assertTrue(has_state_resolved_roadmap_guard(prompt))
        expected = {key: self.config[key] for key in ("id", "cwds", "target", "execution_environment")}
        old = {**self.config, "prompt": render_prompt("entrypoints", LEGACY_PROMPTS["phase-6-v2"])}
        snapshot = runner_snapshot(old, source="isolated fixture", revision="v2")
        plan = plan_migration(snapshot, expected, "entrypoints", self.approval)
        self.assertEqual(plan["issues"], [])
        self.assertEqual(plan["after"], {**old, "prompt": prompt})
        self.assertEqual(plan["versions"]["prompt_template"], VERSIONS["prompt_template"])
        self.assertEqual(plan["provenance"]["prompt_source"], "phase-6-v2")
        human_edit = {**old, "prompt": old["prompt"] + "\nKeep my custom restriction."}
        unknown = plan_migration(runner_snapshot(human_edit, source="fixture", revision="human"),
                                 expected, "entrypoints", self.approval)
        self.assertIn("unknown_prompt_provenance", unknown["issues"])

    def test_progress_cli_helper_retries_and_second_no_progress_stall(self):
        common = self.common()
        first = self.execute(self.codex, "roadmap_delivery.py", "progress", *common, "--start-run", "--run-id", "run-one")
        duplicate = self.execute(self.claude_skill, "compute_progress_signature.py", *common, "--start-run", "--run-id", "run-one")
        self.assertEqual(first["active_run"], duplicate["active_run"]); self.assertTrue(duplicate["duplicate"])
        result = self.execute(self.codex, "roadmap_delivery.py", "progress", *common, "--record-run", "--run-id", "run-one")
        repeated = self.execute(self.claude_skill, "compute_progress_signature.py", *common, "--record-run", "--run-id", "run-one")
        self.assertEqual(result["run_count"], 1); self.assertEqual(repeated["stalled_run_count"], 1)
        self.execute(self.claude_skill, "roadmap_delivery.py", "progress", *common, "--start-run", "--run-id", "run-two")
        stalled = self.execute(self.codex, "compute_progress_signature.py", *common, "--record-run", "--run-id", "run-two")
        self.assertTrue(stalled["threshold_reached"]); self.assertEqual(stalled["run_count"], 2)
        self.assertEqual(stalled["terminal_plan"]["stage"], "terminal_reconciliation")
        self.assertFalse(stalled["terminal_plan"]["extract_phase"])

    def test_claude_hook_allows_terminal_closeout_and_uses_shared_decision(self):
        self.state.update(status="completed_pending_pause")
        self.approval = default_approval_policy("delegated_local", pause_on_completion=False)
        self.save()
        proc = subprocess.run([sys.executable, "-I", "-S", str(self.claude / "hooks/roadmap_delivery_safety.py"), "remind-prompt"],
            input=json.dumps({"cwd": str(self.repo), "prompt": "Deliver roadmap entrypoints"}),
            cwd=self.repo, env=self.env, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        response = json.loads(proc.stdout)
        self.assertNotEqual(response.get("decision"), "block")
        context = response["hookSpecificOutput"]["additionalContext"]
        plan = json.loads(context.split("control_plan: ", 1)[1])
        self.assertEqual(semantic(plan), semantic(self.canonical()))
        self.assertEqual(plan["action"], "record_disabled")

    def test_terminal_planners_do_not_require_roadmap_or_propose_advancement(self):
        for status, stalls in (("completed_pending_pause", 0), ("blocked", 2)):
            self.state.update(status=status, stalled_run_count=stalls)
            self.save()
            # Ordinary phase inputs are deliberately unavailable; terminal
            # alert/readback handling must still be inspectable.
            (self.repo / "roadmaps/in_progress_entrypoints.md").unlink(missing_ok=True)
            (self.directory / "phase_model_policy.json").unlink()
            for skill in (self.codex, self.claude_skill):
                retarget = self.execute(skill, "plan_automation_retarget.py", *self.common())
                self.assertEqual(retarget["state_updates"], {})
                self.assertFalse(retarget["retarget"]["update_required"])
                self.assertIsNone(retarget["next_phase"])
                self.assertEqual(retarget["errors"], [])
                preflight = self.execute(skill, "plan_phase_prerequisites.py", *self.common())
                self.assertEqual(preflight["phases"], [])
                self.assertEqual(preflight["errors"], [])
                self.assertEqual(semantic(retarget["control_plan"]), semantic(preflight["control_plan"]))
                self.assertEqual(retarget["control_plan"]["stage"], "terminal_reconciliation")

    def test_helpers_import_policy_instead_of_copying_implementations(self):
        for name in ("plan_phase_prerequisites.py", "plan_automation_retarget.py"):
            tree = ast.parse((ROOT / "adapters/codex/templates/scripts" / name).read_text())
            self.assertFalse(any(isinstance(node, (ast.FunctionDef, ast.ClassDef)) for node in tree.body))
            spec = importlib.util.spec_from_file_location(name[:-3], ROOT / "adapters/codex/templates/scripts" / name)
            module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
            from roadmap_delivery.control import decide_control
            self.assertIs(module.decide_control, decide_control)


if __name__ == "__main__":
    unittest.main()
