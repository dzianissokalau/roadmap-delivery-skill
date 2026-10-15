"""Offline host double loaded by an extracted skill under Python -I -S.

No checkout runtime or test helper imports are allowed in this process. Inputs
and effects stay under the explicitly supplied temporary project root.
"""
import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import re
import runpy
import subprocess
import sys
from unittest.mock import patch


skill, root = map(lambda value: Path(value).resolve(), sys.argv[1:3])
runpy.run_path(str(skill / "scripts/roadmap_delivery.py"))

from roadmap_delivery import adaptive, approval, automation, control, progress
from roadmap_delivery.approval import default_approval_policy
from roadmap_delivery.cli import main
from roadmap_delivery.migrations import LEGACY_PROMPTS, plan_migration, render_prompt, resume_migration
from roadmap_delivery.policy import has_state_resolved_roadmap_guard, has_hard_stop_guard, has_blocked_remediation_guard
from roadmap_delivery.scaffold import ScaffoldOptions, build_scaffold_plan, apply_scaffold_plan
from roadmap_delivery.state import load_json_object, write_json_object
from roadmap_delivery.toml import parse_toml


inputs = json.load(sys.stdin)
directory = root / "automation/scenario"
path = directory / "delivery_state.json"
host_path = root / "host.json"


def save(target, value):
    write_json_object(target, value)


def state():
    return load_json_object(path)


def update(**changes):
    value = state(); value.update(changes); save(path, value)
    return value


def sha(target):
    return hashlib.sha256(target.read_bytes()).hexdigest()


class FakeScheduler:
    """Persistent observable CAS/idempotency fake, never a live host adapter."""
    def __init__(self):
        self.data = load_json_object(host_path)

    def persist(self):
        save(host_path, self.data)

    def readback(self, runner_id):
        assert runner_id == self.data["config"]["id"]
        self.data["reads"] += 1; self.persist()
        return automation.runner_snapshot(self.data["config"], source="offline scenario scheduler double",
                                          revision=str(self.data["revision"]))

    def apply(self, request):
        if request["request_id"] in self.data["applied"]:
            return
        if request["expected_revision"] != str(self.data["revision"]):
            raise automation.RunnerError("stale_revision", "Scenario CAS rejected stale plan.")
        self.data["requests"].append(copy.deepcopy(request)); self.persist()
        if inputs.get("reject"):
            raise automation.RunnerError("transient_failure", "Scenario host unavailable.", transient=True)
        self.data["config"] = copy.deepcopy(request["payload"])
        self.data["revision"] += 1
        self.data["applied"].append(request["request_id"]); self.persist()
        if inputs.get("lose_ack"):
            raise OSError("Scenario lost acknowledgement after effect.")

    pause_status_only = apply
    update_prompt_only = apply


def cli(*args):
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        code = main(list(args))
    return code, json.loads(output.getvalue())


def setup():
    root.mkdir(parents=True, exist_ok=True)
    plan = build_scaffold_plan(ScaffoldOptions(root, "scenario", automation_id="scenario",
        initial_model="fixture-model", reasoning_effort="high", initial_phase="Phase 0 - Fixture"))
    assert not plan["errors"], plan
    apply_scaffold_plan(plan)
    assert state()["configured_automation_model"] is None and state()["configured_automation_reasoning_effort"] is None
    config = {"id": "scenario", "status": "ACTIVE", "model": "fixture-model", "reasoning_effort": "xhigh",
        "prompt": render_prompt("scenario"), "rrule": "FREQ=HOURLY", "execution_environment": "local",
        "cwds": [str(root)], "target": {"type": "project", "project_id": str(root)},
        "notificationPolicy": "failed_runs_only", "unknown": {"retained": [1, True, "value"]}}
    save(host_path, {"config": config, "revision": 1, "requests": [], "applied": [], "reads": 0})
    update(automation={"id": "scenario", "kind": "cron", "project_id": str(root), "cwd": str(root),
        "execution_environment": "local", "status": "PAUSED"}, configured_automation_status="PAUSED",
        required_model="fixture-model", required_reasoning_effort="high")
    return FakeScheduler()


def runner(host):
    config = host.readback("scenario")["config"]
    return {"kind": "cron", "expected": {"id": "scenario", "project_id": str(root), "cwd": str(root),
        "execution_environment": "local"}, "observed": {"id": config["id"], "project_id": config["target"]["project_id"],
        "cwd": config["cwds"][0], "execution_environment": config["execution_environment"], "status": config["status"],
        "model": config["model"], "reasoning_effort": config["reasoning_effort"],
        "prompt_guards": {"state_first": has_state_resolved_roadmap_guard(config["prompt"]),
            "terminal": has_hard_stop_guard(config["prompt"]),
            "blocked_remediation": has_blocked_remediation_guard(config["prompt"])}}}


def activate(host):
    policy = load_json_object(directory / "approval_policy.json")
    observed = runner(host)
    decision = control.decide_control(state(), policy, {"prerequisites_passed": True}, observed)
    assert decision["reason_code"] == "intentional_operator_activation", decision
    update(configured_automation_status="ACTIVE", automation={**state()["automation"], "status": "ACTIVE"})
    decision = control.decide_control(state(), policy, {"prerequisites_passed": True}, observed)
    assert decision["extract_phase"] and decision["result"] == "ready", decision
    return decision


def evidence(kind="accepted_phase_work", criterion="C-fixture", increment="work-1"):
    artifact = root / "work.py"; artifact.write_text("print('fixture acceptance passed')\n")
    verification = subprocess.run([sys.executable, "-I", "-S", str(artifact)], cwd=root,
                                  capture_output=True, text=True, timeout=10)
    assert verification.returncode == 0 and verification.stdout == "fixture acceptance passed\n", verification.stderr
    check = root / "verification.txt"; check.write_text(verification.stdout)
    review = directory / "review.md"; review.write_text(f"Verdict: delivered\n{criterion}: accepted\n")
    item = {"schema_version": 1, "phase": state()["current_phase"], "kind": kind,
        "previous": {"status": "unmet"}, "current": {"status": "accepted", "artifact": "work.py", "artifact_sha256": sha(artifact)}}
    if kind == "accepted_phase_work":
        item.update(criterion_id=criterion, increment_id=increment)
    else:
        item.update(blocker_id="missing-input", previous={"status": "blocked", "blocked_reason": state()["active_run"]["blocked_reason"],
                                                        "blocker_occurrence_id": state()["active_run"]["blocker_occurrence_id"]})
        item["current"]["status"] = "resolved"
    verifier = root / "verifier.json"
    save(verifier, {"schema_version": 1, "result": "verified", "evidence": [item],
        "check": {"path": "verification.txt", "sha256": sha(check), "result": "passed"},
        "review": {"path": str(review.relative_to(root)), "sha256": sha(review)}})
    return [{**item, "verifier": {"path": "verifier.json", "sha256": sha(verifier)}}]


def terminal():
    # Terminal-only failure fixtures supply upstream evidence. The complete
    # workflow retains the actual fixture command output created by evidence().
    if not (root / "verification.txt").exists():
        (root / "verification.txt").write_text("Offline supplied terminal fixture evidence\n")
    (directory / "review.md").write_text("Verdict: delivered\n")
    (directory / "final-deep-review.md").write_text("Review all delivered fixture phases independently.\n")
    update(status="completed_pending_pause", all_phases_complete=True, current_phase="finalization",
        last_verification={"status": "passed", "output_file": "verification.txt"},
        last_review={"verdict": "delivered", "file": "automation/scenario/review.md"},
        final_deep_review_prompt_prepared=True, final_deep_review_prompt_file="automation/scenario/final-deep-review.md")


def full():
    host = setup(); activate(host)
    run_id = "accepted-run"
    started = progress.start_run(root, path, run_id, owned_files=["work.py"])
    assert started["started"]
    ev = evidence()
    outcome = progress.record_run_result(root, path, run_id=run_id, semantic_evidence=ev)
    assert outcome["progress_detected"] and state()["run_count"] == 1
    duplicate = progress.record_run_result(root, path, run_id=run_id)
    assert duplicate["duplicate"] and state()["run_count"] == 1
    policy = load_json_object(directory / "approval_policy.json")
    incomplete = control.decide_control(state(), policy, {"prerequisites_passed": True}, runner(host), event="advance_phase")
    assert incomplete["reason_code"] == "delivery_gate_incomplete"
    phase = state()["current_phase"]
    accepted = control.decide_control(state(), policy, {"prerequisites_passed": True, "review_verdict": "delivered",
        "acceptance_passed": True, "verification_passed": True, "review_fresh": True,
        "review_file": "automation/scenario/review.md", "review_phase": phase}, runner(host), event="advance_phase")
    assert accepted["action"] == "prepare_finalization" and not accepted["extract_phase"]
    update(**accepted["proposed_state_changes"]); terminal()
    before = copy.deepcopy(host.data["config"])
    pending = automation.resume_terminal_closeout(root, path, observed=host.readback("scenario"))
    assert not pending["completion_claim"] and pending["receipt"] is None
    host.pause_status_only(pending["action_request"])
    snapshot_path = root / "observed.json"; save(snapshot_path, host.readback("scenario"))
    code, result = cli("terminal-closeout", "--repo-root", str(root), "--state-file", str(path),
                       "--runner-snapshot", str(snapshot_path), "--json")
    assert code == 0 and result["completion_claim"] and result["receipt"]["readback_status"] == "PAUSED", result
    assert host.data["config"] == {**before, "status": "PAUSED"}
    repeat = automation.resume_terminal_closeout(root, path, adapter=host)
    assert repeat["completion_claim"] and len(host.data["applied"]) == 1
    assert len(list((directory / "alerts").glob("*.md"))) == 1
    try:
        progress.start_run(root, path, "forbidden-extra-phase")
    except progress.ProgressSignatureError:
        pass
    else:
        raise AssertionError("Terminal state permitted duplicate phase work")
    return {"state": state(), "host": host.data, "origins": origins()}


def blockers(repair=False):
    host = setup(); activate(host)
    update(status="blocked", blocked_reason="Missing fixture input")
    policy = load_json_object(directory / "approval_policy.json")
    first = control.decide_control(state(), policy, {"blocker_class": "local-repairable"}, runner(host))
    assert first["action"] == "repair_blocker" and not first["extract_phase"]
    progress.start_run(root, path, "run-1", owned_files=["work.py"])
    result = progress.record_run_result(root, path, run_id="run-1")
    assert result["stalled_run_count"] == 1 and state()["blocked_reason"] == "Missing fixture input", "regression-probe:R1:" + json.dumps(result)
    # Fresh log/review names and harmless bookkeeping must not reset progress.
    (directory / "delivery_log.md").write_text("Another retry with a new timestamp\n")
    (directory / "review-2.md").write_text("Verdict: blocked\nSame missing input\n")
    update(last_review={"file": "automation/scenario/review-2.md", "verdict": "blocked"}, updated_at="later")
    progress.start_run(root, path, "run-2", owned_files=["work.py"])
    if repair:
        result = progress.record_run_result(root, path, run_id="run-2", semantic_evidence=evidence("blocker_resolved"))
        assert result["progress_detected"] and state()["blocked_reason"] is None and state()["stalled_run_count"] == 0
        assert progress.record_run_result(root, path, run_id="run-2")["duplicate"]
        progress.start_run(root, path, "run-3", owned_files=["work.py"])
        result = progress.record_run_result(root, path, run_id="run-3")
        assert result["stalled_run_count"] == 1
    else:
        result = progress.record_run_result(root, path, run_id="run-2")
        assert result["stalled_run_count"] == 2 and result["threshold_reached"], result
        assert not result["terminal_plan"]["extract_phase"]
        closed = automation.resume_terminal_closeout(root, path, adapter=host)
        assert closed["receipt"]["paused"] and state()["blocked_reason"] == "Missing fixture input"
        assert state()["run_count"] == 2 and state()["stalled_run_count"] == 2
        try:
            progress.start_run(root, path, "run-3")
        except progress.ProgressSignatureError:
            pass
        else:
            raise AssertionError("Stall threshold allowed more phase work")
    return {"state": state(), "host": host.data}


def mutation(regression):
    if regression == "R1":
        original = progress.account_run_outcome
        def old_account(*args, **kwargs):
            result = original(*args, **kwargs)
            result["proposed_state_changes"]["stalled_run_count"] = 0
            return result
        return patch.object(progress, "account_run_outcome", old_account)
    if regression == "R3":
        original = control.decide_control
        def old_terminal_gate(state, policy=None, *args, **kwargs):
            result = original(state, policy, *args, **kwargs)
            # The old instruction/planner requires broad saved-config approval
            # even for an otherwise authorized completion status-only pause.
            if state.get("all_phases_complete") and policy.get("operations", {}).get("pause_saved_automation") is False:
                result.update(action="record_required_action", result="permission_required", reason_code="legacy_broad_saved_config_gate")
            return result
        return patch.object(control, "decide_control", old_terminal_gate)
    if regression == "R5":
        original = control.approval_decision_for_pause_context
        def old_pause(report, context, **kwargs):
            decision = original(report, context, **kwargs)
            return {**decision, "decision": "allowed", "reason_code": "legacy_broad_mode"}
        stack = contextlib.ExitStack()
        stack.enter_context(patch.object(control, "approval_decision_for_pause_context", old_pause))
        stack.enter_context(patch.object(approval, "approval_decision_for_pause_context", old_pause))
        return stack
    if regression == "R4":
        def old_status(text, status):
            pattern = r'^status\s*=\s*"[^"]*"\s*$'
            return re.sub(pattern, f'status = "{status}"', text, flags=re.M) if re.search(pattern, text, re.M) else text + f'\nstatus = "{status}"\n'
        return patch.object(automation, "_replace_status", old_status)
    if regression == "R6":
        original = adaptive.resolve_adaptive_action
        def old_target(*args, **kwargs):
            result = original(*args, **kwargs)
            result["target"]["reasoning_effort"] = "low"
            return result
        return patch.object(adaptive, "resolve_adaptive_action", old_target)
    raise ValueError(regression)


def regression_probe(regression):
    if regression == "R1":
        return blockers()
    host = setup(); activate(host)
    if regression == "R3":
        host.data["config"]["prompt"] = render_prompt("scenario", LEGACY_PROMPTS["9c0d7ae^"], roadmap=state()["roadmap"])
        host.persist()
        before = copy.deepcopy(host.data["config"])
        expected = {k: before[k] for k in ("id", "cwds", "target", "execution_environment")}
        plan = plan_migration(host.readback("scenario"), expected, "scenario", default_approval_policy(), roadmap=state()["roadmap"], policy_path=str(directory / "approval_policy.json"))
        assert plan["status"] == "planned"
        refused = resume_migration(plan, directory / "migration.json", adapter=host, policy_path=directory / "approval_policy.json")
        assert refused["status"] == "needs-decision" and not host.data["requests"], refused
        authority = {"authorized": True, "runner_id": "scenario", "plan_id": plan["plan_id"], "direction": "forward",
            "effects": plan["effects"], "source": "isolated fixture operator authorization"}
        migrated = resume_migration(plan, directory / "migration.json", adapter=host, authority=authority,
                                    policy_path=directory / "approval_policy.json")
        assert migrated["status"] == "verified", migrated
        assert host.data["config"] == {**before, "prompt": render_prompt("scenario")}
        terminal()
        closed = automation.resume_terminal_closeout(root, path, adapter=host)
        assert closed["receipt"] and closed["receipt"]["paused"] and closed["completion_claim"], "regression-probe:R3:" + json.dumps(closed)
    elif regression == "R4":
        folder = root / "file-runners/scenario"; folder.mkdir(parents=True)
        config_path = folder / "automation.toml"
        text = 'id = "scenario"\nstatus = "ACTIVE" # operator activation\nprompt = """Preserve this\nstatus = "ACTIVE"\n"""\n[unknown]\nvalue = [1, true]\n'
        config_path.write_text(text)
        before = parse_toml(text)
        adapter = automation.FileRunnerAdapter(root / "file-runners", host_contract="isolated documented fixture backend")
        result = automation.pause_saved_automation("scenario", adapter=adapter)
        assert result["paused"], "regression-probe:R4:" + json.dumps(result)
        assert parse_toml(config_path.read_text()) == {**before, "status": "PAUSED"}
    elif regression == "R5":
        terminal()
        policy = default_approval_policy("delegated_delivery", pause_on_completion=False, pause_on_stall=False)
        save(directory / "approval_policy.json", policy)
        closed = automation.resume_terminal_closeout(root, path, adapter=host)
        assert closed["status"] == "disabled" and not host.data["requests"] and not closed["completion_claim"], "regression-probe:R5:" + json.dumps(closed)
    elif regression == "R6":
        policy = load_json_object(directory / "phase_model_policy.json")
        policy["adaptive_model_policy"] = {"enabled": True, "floors": {"min_reasoning_effort": "high"},
            "caps": {"allowed_models": ["fixture-model"], "max_reasoning_effort": "xhigh"},
            "deescalate_after_flawless_runs": 1, "deescalation": {"model": "fixture-model", "reasoning_effort": "low"}}
        result = adaptive.resolve_adaptive_action(policy, base_model="fixture-model", base_reasoning_effort="high", run_quality="flawless")
        assert not result["errors"] and result["target"]["reasoning_effort"] == "high", "regression-probe:R6:" + json.dumps(result)
        policy["adaptive_model_policy"]["caps"]["max_reasoning_effort"] = "medium"
        conflict = adaptive.resolve_adaptive_action(policy, base_model="fixture-model", base_reasoning_effort="high", run_quality="flawless")
        assert conflict["errors"] and conflict["target"] is None
    return {"regression": regression, "passed": True}


def origins():
    result = {name: value.__file__ for name, value in sys.modules.items()
              if name.startswith("roadmap_delivery") and hasattr(value, "__file__")}
    assert all(Path(value).is_relative_to(skill / "runtime") for value in result.values()), result
    assert not any("site-packages" in value for value in sys.path), sys.path
    return result


def journal_recovery():
    host = setup(); activate(host)
    for moment in ("start", "outcome"):
        run_id = "interrupted-" + moment
        if moment == "outcome":
            progress.start_run(root, path, run_id, owned_files=["work.py"])
        with patch.object(progress, "write_progress_json_object", side_effect=progress.ProgressSignatureError("partial state write")):
            try:
                if moment == "start":
                    progress.start_run(root, path, run_id, owned_files=["work.py"])
                else:
                    progress.record_run_result(root, path, run_id=run_id, semantic_evidence=evidence(increment="recovery"))
            except progress.ProgressSignatureError:
                pass
            else:
                raise AssertionError("Failure injection did not interrupt state write")
        if moment == "start":
            assert progress.start_run(root, path, run_id)["duplicate"]
            progress.record_run_result(root, path, run_id=run_id, semantic_evidence=evidence())
        else:
            assert progress.record_run_result(root, path, run_id=run_id)["duplicate"]
    assert state()["run_count"] == 2 and state()["active_run"] is None
    revision = state()["progress_accounting"]["revision"]
    progress.start_run(root, path, "writer-one", expected_revision=revision)
    before = path.read_bytes()
    try:
        progress.start_run(root, path, "stale-writer", expected_revision=revision)
    except progress.ProgressSignatureError:
        pass
    else:
        raise AssertionError("Concurrent stale plan was accepted")
    assert path.read_bytes() == before
    progress.record_run_result(root, path, run_id="writer-one")
    assert state()["run_count"] == 3
    terminal(); host.persist()
    request = automation.prepare_pause_request(host.readback("scenario"), {"id": "scenario"}, "stale-request")
    host.data["config"]["notificationPolicy"] = "human-preference"; host.data["revision"] += 1; host.persist()
    try:
        host.pause_status_only(request)
    except automation.RunnerError as exc:
        assert exc.code == "stale_revision"
    else:
        raise AssertionError("Stale runner plan overwrote a preference")
    assert host.data["config"]["status"] == "ACTIVE" and not host.data["requests"]
    return {"state": state(), "host": host.data}


def policy_cross():
    host = setup(); activate(host)
    stalled = inputs.get("stalled", False)
    if stalled:
        update(status="blocked", blocked_reason="Original fixture blocker", stalled_run_count=2, run_count=2)
    else:
        terminal()
    mode = inputs["mode"]
    if mode == "missing":
        (directory / "approval_policy.json").unlink()
    else:
        policy = default_approval_policy(mode, {"pause_saved_automation": True} if mode == "custom" else None)
        if inputs["optout"]:
            policy["pause_automation_on_stall" if stalled else "pause_automation_on_completion"] = False
        save(directory / "approval_policy.json", policy)
    result = automation.resume_terminal_closeout(root, path, adapter=host)
    disabled = mode != "missing" and inputs["optout"]
    assert result["status"] == ("disabled" if disabled else "paused"), result
    assert bool(host.data["requests"]) == (not disabled)
    assert state()["blocked_reason"] == ("Original fixture blocker" if stalled else None)
    return {"result": result, "host": host.data}


action = inputs["action"]
if action == "full":
    result = full()
elif action == "blockers":
    result = blockers(inputs.get("repair", False))
elif action == "journal":
    result = journal_recovery()
elif action == "policy":
    result = policy_cross()
elif action == "regression":
    regression = inputs["regression"]
    with mutation(regression) if inputs.get("mutate") else contextlib.nullcontext():
        result = regression_probe(regression)
elif action == "prepare-terminal":
    setup(); terminal(); result = {"state": state()}
elif action == "closeout":
    def crash(point):
        if point == inputs.get("failpoint"):
            raise RuntimeError("scenario-crash:" + point)
    result = automation.resume_terminal_closeout(root, path, adapter=FakeScheduler(), failpoint=crash)
else:
    raise ValueError(action)
result["origins"] = origins()
print(json.dumps(result, sort_keys=True))
