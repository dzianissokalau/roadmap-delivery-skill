"""Resumable terminal effects, tested without any live scheduler access."""
import copy
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from roadmap_delivery.approval import default_approval_policy
from roadmap_delivery.automation import RunnerError, resume_terminal_closeout
from roadmap_delivery.cli import main
from roadmap_delivery.state import load_json_object, write_json_object
from tests.test_runner_updates import CONFIG, FakeRunner


class Crash(RuntimeError):
    pass


class TerminalCloseoutTests(unittest.TestCase):
    def fixture(self, root, *, stalled=False, manual=False, policy=None):
        directory = root / "automation" / "fixture"; directory.mkdir(parents=True)
        for name in ("verification.txt", "review.md", "final-deep-review.md"):
            (directory / name).write_text("Verdict: delivered\n" if name == "review.md" else "final evidence\n")
        state = {
            "schema_version": 1, "roadmap": "roadmaps/fixture.md", "roadmap_slug": "fixture",
            "current_phase": "Finalization", "status": "blocked" if stalled else "completed_pending_pause",
            "all_phases_complete": not stalled, "run_count": 2, "stalled_run_count": 2 if stalled else 0,
            "max_stalled_runs": 2, "blocked_reason": "Original actionable cause" if stalled else None,
            "automation": {"id": "fixture", "kind": "manual" if manual else "cron", "project_id": "fixture-project",
                           "cwd": "/isolated/repo", "execution_environment": "local", "status": "ACTIVE"},
            "last_completed_run_id": "run-2", "configured_automation_status": "ACTIVE",
            "required_model": "stronger-than-cleanup", "required_reasoning_effort": "xhigh",
            "last_verification": {"status": "passed", "output_file": str(directory / "verification.txt")},
            "last_review": {"verdict": "delivered", "file": str(directory / "review.md")},
            "final_deep_review_prompt_prepared": True, "final_deep_review_prompt_file": str(directory / "final-deep-review.md"),
        }
        path = directory / "delivery_state.json"; write_json_object(path, state)
        (directory / "approval_policy.json").write_text(json.dumps(default_approval_policy("conservative") if policy is None else policy))
        (directory / "delivery_log.md").write_text("# Delivery Log\n")
        return path

    def assert_reconciled(self, root, path, host, *, stalled=False):
        state = load_json_object(path); journal = load_json_object(path.parent / "terminal_closeout.json")
        self.assertEqual(host.config["status"], "PAUSED")
        self.assertEqual(state["terminal_closeout"]["receipt"]["readback_status"], "PAUSED")
        self.assertEqual(state["terminal_closeout"], journal["state_changes"]["terminal_closeout"])
        self.assertEqual(state["status"], "blocked" if stalled else "completed")
        self.assertEqual(state["run_count"], 2)
        self.assertEqual(state["stalled_run_count"], 2 if stalled else 0)
        self.assertEqual(state["blocked_reason"], "Original actionable cause" if stalled else None)
        self.assertEqual(len(list((path.parent / "alerts").glob("*.md"))), 1)
        self.assertTrue((root / state["last_operator_alert"]["file"]).is_file())
        self.assertEqual(state["last_automation_pause"]["source"], "isolated fake host")
        self.assertEqual(len(host.applied), 1)
        self.assertFalse((path.parent / "automation_run_log.jsonl").exists())
        self.assertIn("Terminal receipt:", (path.parent / "delivery_log.md").read_text())

    def test_default_completion_and_stall_pause_without_model_gate(self):
        for stalled in (False, True):
            with self.subTest(stalled=stalled), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); path = self.fixture(root, stalled=stalled); host = FakeRunner()
                result = resume_terminal_closeout(root, path, adapter=host)
                self.assertTrue(result["receipt"]["paused"])
                self.assertFalse(result["extract_phase"])
                self.assertEqual(result["completion_claim"], not stalled)
                self.assert_reconciled(root, path, host, stalled=stalled)
                log = (path.parent / "delivery_log.md").read_bytes()
                repeat = resume_terminal_closeout(root, path, adapter=host)
                self.assertEqual(repeat["intent_id"], result["intent_id"])
                self.assertEqual(len(host.requests), 1)
                self.assertEqual(log, (path.parent / "delivery_log.md").read_bytes())

    def test_crash_before_after_every_effect_converges(self):
        points = ("after_journal_intent", "after_state_intent", "before_alert", "after_alert", "after_journal_alert", "after_state_alert",
                  "before_readback", "after_readback", "after_journal_request", "after_state_request", "before_pause", "after_pause",
                  "before_receipt_readback", "after_receipt_readback", "after_journal_receipt", "after_state_receipt", "before_log", "after_log")
        for stalled in (False, True):
            for point in points:
                with self.subTest(point=point, stalled=stalled), tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp); path = self.fixture(root, stalled=stalled); host = FakeRunner()
                    def crash(here):
                        if here == point: raise Crash(here)
                    with self.assertRaises(Crash): resume_terminal_closeout(root, path, adapter=host, failpoint=crash)
                    resume_terminal_closeout(root, path, adapter=host)
                    self.assert_reconciled(root, path, host, stalled=stalled)
                    before = (path.parent / "delivery_log.md").read_bytes()
                    resume_terminal_closeout(root, path, adapter=host)
                    self.assertEqual(before, (path.parent / "delivery_log.md").read_bytes())

    def test_context_optouts_leave_runner_untouched_in_all_modes(self):
        for mode in ("conservative", "delegated_local", "delegated_delivery"):
            for stalled in (False, True):
                with self.subTest(mode=mode, stalled=stalled), tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp); policy = default_approval_policy(mode, pause_on_completion=False, pause_on_stall=False)
                    path = self.fixture(root, stalled=stalled, policy=policy); host = FakeRunner()
                    result = resume_terminal_closeout(root, path, adapter=host)
                    self.assertEqual(result["status"], "disabled")
                    self.assertEqual(host.reads, 0); self.assertEqual(host.requests, [])
                    self.assertFalse(result["completion_claim"])
                    self.assertEqual(len(list((path.parent / "alerts").glob("*.md"))), 1)

    def test_missing_policy_defaults_pause_and_invalid_policy_cannot_mutate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); path = self.fixture(root); (path.parent / "approval_policy.json").unlink(); host = FakeRunner()
            self.assertEqual(resume_terminal_closeout(root, path, adapter=host)["status"], "paused")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); path = self.fixture(root, policy={"operations": "malformed"}); host = FakeRunner()
            result = resume_terminal_closeout(root, path, adapter=host)
            self.assertEqual(result["status"], "invalid_input"); self.assertEqual(host.requests, [])
            self.assertFalse(result["completion_claim"])

    def test_already_paused_manual_and_unscheduled_are_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); path = self.fixture(root); host = FakeRunner({**CONFIG, "status": "PAUSED"})
            result = resume_terminal_closeout(root, path, adapter=host)
            self.assertEqual(result["status"], "already_paused"); self.assertTrue(result["completion_claim"])
            self.assertEqual(host.requests, [])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); path = self.fixture(root, manual=True); host = FakeRunner()
            result = resume_terminal_closeout(root, path, adapter=host)
            self.assertEqual(result["status"], "not_applicable"); self.assertTrue(result["completion_claim"])
            self.assertEqual(host.reads, 0); self.assertIsNone(result["receipt"])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); path = self.fixture(root); state = load_json_object(path); state['automation'] = None; write_json_object(path,state)
            result = resume_terminal_closeout(root, path)
            self.assertFalse(result["completion_claim"])
            self.assertIsNone(result["receipt"]); self.assertTrue(result["required_action"])

    def test_missing_final_evidence_pauses_but_cannot_claim_completion(self):
        for field in ("last_verification", "last_review", "final_deep_review_prompt_file"):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); path = self.fixture(root); state = load_json_object(path); state[field] = None; write_json_object(path,state)
                result = resume_terminal_closeout(root, path, adapter=FakeRunner())
                self.assertTrue(result["receipt"]["paused"])
                self.assertFalse(result["completion_claim"])
                self.assertEqual(result["state_status"], "completed_pending_pause")
                self.assertIn("final verification", result["required_action"])

    def test_unreadable_review_never_prevents_safety_pause(self):
        for stalled in (False, True):
            for failure in (UnicodeDecodeError("utf8", b"\xff", 0, 1, "invalid"), OSError("read denied"), FileNotFoundError("removed")):
                with self.subTest(stalled=stalled, failure=type(failure)), tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp); path = self.fixture(root, stalled=stalled); host = FakeRunner()
                    original = Path.read_text
                    def read(file, *args, **kwargs):
                        if file.name == "review.md": raise failure
                        return original(file, *args, **kwargs)
                    with patch.object(Path, "read_text", read):
                        result = resume_terminal_closeout(root, path, adapter=host)
                    self.assertEqual(host.config["status"], "PAUSED")
                    self.assertTrue(result["receipt"]["paused"])
                    self.assertFalse(result["completion_claim"])
                    diagnostics = load_json_object(path)["terminal_closeout"]["evidence_diagnostics"]
                    self.assertEqual(bool(diagnostics), not stalled)

    def test_readback_mismatch_and_settings_drift_stop_effects(self):
        for changes in ({"id":"wrong"}, {"target":{"type":"project","project_id":"other"}}, {"cwds":["/elsewhere"]}):
            with self.subTest(changes=changes), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); path = self.fixture(root); host = FakeRunner({**CONFIG, **changes})
                result = resume_terminal_closeout(root, path, adapter=host)
                self.assertEqual(result["status"], "identity_mismatch"); self.assertEqual(host.requests, [])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); path = self.fixture(root); host = FakeRunner(); host.change_setting=True
            result = resume_terminal_closeout(root, path, adapter=host)
            self.assertEqual(result["status"], "settings_changed"); self.assertIsNone(result["receipt"])
            self.assertFalse(result["completion_claim"])
            self.assertEqual(load_json_object(path)['last_automation_pause']['readback_status'], 'PAUSED')
            self.assertEqual(load_json_object(path)['terminal_closeout']['last_readback']['config']['model'], 'other-model')

    def test_rejection_and_transient_failures_are_bounded_and_resumable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); path = self.fixture(root); host = FakeRunner(); host.reject = RunnerError("permission_required", "Host rejected permission.")
            for _ in range(3):
                result = resume_terminal_closeout(root,path,adapter=host)
                self.assertEqual(result['status'], 'permission_required'); self.assertIsNone(result['receipt'])
            self.assertEqual(len(host.requests),1)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); path=self.fixture(root); host=FakeRunner(); host.reject=RunnerError('transient_failure','Temporarily unavailable.',transient=True)
            for _ in range(4): result=resume_terminal_closeout(root,path,adapter=host)
            self.assertEqual(len(host.requests),2); self.assertEqual(result['attempts'],2)
            self.assertEqual(result['status'],'retry_exhausted'); self.assertIn('supported host tool',result['required_action'])
            host.config['status']='PAUSED'; host.revision+=1
            result=resume_terminal_closeout(root,path,adapter=host)
            self.assertTrue(result['receipt']['paused']); self.assertTrue(result['completion_claim'])
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); path=self.fixture(root); host=FakeRunner();host.lose_ack=True
            result=resume_terminal_closeout(root,path,adapter=host)
            self.assertFalse(result['completion_claim'])
            result=resume_terminal_closeout(root,path,adapter=host)
            self.assertTrue(result['receipt']['paused']);self.assertEqual(len(host.requests),1)

    def test_action_request_replay_and_cli_receipt_never_infer_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=self.fixture(root);host=FakeRunner();observed=host.readback('fixture')
            first=resume_terminal_closeout(root,path,observed=observed)
            second=resume_terminal_closeout(root,path,observed=observed)
            self.assertIsNotNone(first['action_request']);self.assertIsNone(second['action_request']);self.assertEqual(second['attempts'],1)
            self.assertIsNone(second['receipt']);self.assertFalse(second['completion_claim'])
            host.pause_status_only(first['action_request'])
            observation=path.parent/'observation.json';write_json_object(observation,host.readback('fixture'))
            output=io.StringIO()
            with contextlib.redirect_stdout(output):
                code=main(['terminal-closeout','--repo-root',str(root),'--state-file',str(path),'--runner-snapshot',str(observation),'--json'])
            self.assertEqual(code,0);self.assertTrue(json.loads(output.getvalue())['completion_claim'])

    def test_external_attempt_outcomes_bound_retries_without_reissuing_inspection(self):
        for outcome_status in ("acknowledged", "transient_failure", "not_executed"):
            with self.subTest(status=outcome_status), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); path = self.fixture(root); host = FakeRunner(); host.leave_active = True
                result = resume_terminal_closeout(root, path, observed=host.readback("fixture"))
                for attempt in (1, 2):
                    self.assertEqual(result["external_attempt"], attempt)
                    host.pause_status_only(result["action_request"])
                    for _ in range(3):
                        inspection = resume_terminal_closeout(root, path, observed=host.readback("fixture"))
                        self.assertIsNone(inspection["action_request"])
                        self.assertEqual(inspection["attempts"], attempt)
                    outcome = {"request_id": result["intent_id"], "attempt": attempt,
                               "status": outcome_status, "source": "isolated host invocation"}
                    result = resume_terminal_closeout(root, path, observed=host.readback("fixture"), external_outcome=outcome)
                    retry = resume_terminal_closeout(root, path, observed=host.readback("fixture"), external_outcome=outcome)
                    self.assertIsNone(retry["action_request"])
                    self.assertEqual(retry["attempts"], result["attempts"])
                self.assertEqual(result["status"], "retry_exhausted")
                self.assertIsNone(result["receipt"])
                self.assertIsNone(result["action_request"])
                self.assertEqual(len(host.requests), 2)
                self.assertEqual(len(load_json_object(path)["terminal_closeout"]["external_outcomes"]), 2)
                host.config["status"] = "PAUSED"; host.revision += 1
                self.assertTrue(resume_terminal_closeout(root, path, observed=host.readback("fixture"))["completion_claim"])

    def test_external_outcomes_reject_conflicts_and_wrong_request_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); path = self.fixture(root); host = FakeRunner()
            first = resume_terminal_closeout(root, path, observed=host.readback("fixture"))
            outcome = {"request_id": first["intent_id"], "attempt": 1,
                       "status": "permission_required", "source": "isolated host rejection"}
            for change in ({"request_id": "wrong"}, {"attempt": 2}, {"attempt": True}, {"source": ""}):
                before = path.read_bytes()
                with self.assertRaises(RunnerError):
                    resume_terminal_closeout(root, path, observed=host.readback("fixture"), external_outcome={**outcome, **change})
                self.assertEqual(before, path.read_bytes())
            result = resume_terminal_closeout(root, path, observed=host.readback("fixture"), external_outcome=outcome)
            self.assertEqual(result["status"], "permission_required"); self.assertIsNone(result["action_request"])
            with self.assertRaises(RunnerError):
                resume_terminal_closeout(root, path, observed=host.readback("fixture"), external_outcome={**outcome, "status": "acknowledged"})

    def test_cli_records_external_outcome_once_before_reserving_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); path = self.fixture(root); host = FakeRunner()
            first = resume_terminal_closeout(root, path, observed=host.readback("fixture"))
            observed = path.parent / "observed.json"; outcome = path.parent / "outcome.json"
            write_json_object(observed, host.readback("fixture"))
            write_json_object(outcome, {"request_id": first["intent_id"], "attempt": 1,
                                       "status": "transient_failure", "source": "isolated host call"})
            arguments = ["terminal-closeout", "--repo-root", str(root), "--state-file", str(path),
                         "--runner-snapshot", str(observed), "--external-outcome", str(outcome), "--json"]
            for replay in (False, True):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    code = main(arguments)
                result = json.loads(output.getvalue())
                self.assertEqual(code, 4); self.assertEqual(result["attempts"], 2)
                self.assertEqual(result["action_request"] is None, replay)
            self.assertEqual(host.requests, [])

    def test_permanent_effect_rejection_survives_readback_failure(self):
        for transport in ("adapter", "external"):
            with self.subTest(transport=transport), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); path = self.fixture(root); host = FakeRunner()
                if transport == "adapter":
                    host.reject = RunnerError("permission_required", "Host explicitly denied the update.")
                    resume_terminal_closeout(root, path, adapter=host)
                else:
                    first = resume_terminal_closeout(root, path, observed=host.readback("fixture"))
                    resume_terminal_closeout(root, path, observed=host.readback("fixture"), external_outcome={
                        "request_id": first["intent_id"], "attempt": 1, "status": "unsupported", "source": "host rejection"})
                requests = len(host.requests)
                with patch.object(host, "readback", side_effect=OSError("temporary timeout")):
                    result = resume_terminal_closeout(root, path, adapter=host)
                self.assertEqual(result["status"], "transient_failure")
                host.reject = None
                result = resume_terminal_closeout(root, path, adapter=host)
                self.assertEqual(result["status"], "permission_required" if transport == "adapter" else "unsupported")
                self.assertEqual(result["attempts"], 1); self.assertEqual(len(host.requests), requests)
                self.assertTrue(load_json_object(path)["terminal_closeout"]["effect_rejection"])
                host.config["status"] = "PAUSED"; host.revision += 1
                self.assertTrue(resume_terminal_closeout(root, path, adapter=host)["completion_claim"])

    def test_transport_switch_cannot_execute_an_unacknowledged_external_attempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); path = self.fixture(root); host = FakeRunner()
            first = resume_terminal_closeout(root, path, observed=host.readback("fixture"))
            for _ in range(3):
                result = resume_terminal_closeout(root, path, adapter=host)
                self.assertIsNone(result["action_request"])
                self.assertEqual(result["attempts"], 1); self.assertEqual(host.requests, [])
            result = resume_terminal_closeout(root, path, adapter=host, external_outcome={
                "request_id": first["intent_id"], "attempt": 1, "status": "not_executed", "source": "confirmed interrupted host call"})
            self.assertEqual(result["attempts"], 2)
            self.assertEqual(len(host.requests), 1); self.assertTrue(result["completion_claim"])

    def test_nonterminal_and_concurrent_closeout_do_not_allocate_attempts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=self.fixture(root);state=load_json_object(path);state.update(all_phases_complete=False,status='not_started');write_json_object(path,state)
            before=path.read_bytes();host=FakeRunner()
            result=resume_terminal_closeout(root,path,adapter=host)
            self.assertEqual(result['status'],'nonterminal');self.assertEqual(path.read_bytes(),before);self.assertEqual(host.reads,0)
        with tempfile.TemporaryDirectory() as tmp:
            import fcntl
            root=Path(tmp);path=self.fixture(root);host=FakeRunner();before=path.read_bytes()
            with (path.parent/'.progress.lock').open('a') as lock:
                fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
                with self.assertRaisesRegex(RuntimeError,'Another writer'):
                    resume_terminal_closeout(root,path,adapter=host)
            self.assertEqual(path.read_bytes(),before);self.assertEqual(host.requests,[])

    def test_state_replace_failure_recovers_written_journal_before_effect(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=self.fixture(root);host=FakeRunner()
            original=write_json_object
            def fail_state(target,value):
                if target==path: raise OSError('State disk failure')
                original(target,value)
            with patch('roadmap_delivery.automation.write_json_object',side_effect=fail_state):
                with self.assertRaises(OSError): resume_terminal_closeout(root,path,adapter=host)
            self.assertEqual(host.requests,[])
            resume_terminal_closeout(root,path,adapter=host)
            self.assert_reconciled(root,path,host)

    def test_stored_payload_and_journal_corruption_stop_before_any_write(self):
        for corruption in ("payload", "counter", "envelope", "unrelated", "scope"):
            with self.subTest(corruption=corruption), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);path=self.fixture(root);host=FakeRunner()
                resume_terminal_closeout(root,path,observed=host.readback('fixture'))
                journal_path=path.parent/'terminal_closeout.json';journal=load_json_object(journal_path)
                if corruption=='payload': journal['state_changes']['terminal_closeout']['request']['payload']['prompt']='tampered'
                if corruption=='counter': journal['state_changes']['terminal_closeout']['attempts']=-1
                if corruption=='envelope': journal['schema_version']=99
                if corruption=='unrelated': journal['state_changes']['run_count']=99
                if corruption=='scope': journal['state_changes']['automation']['project_id']='other'
                write_json_object(journal_path,journal);before=path.read_bytes()
                with self.assertRaises(RunnerError): resume_terminal_closeout(root,path,adapter=host)
                self.assertEqual(host.requests,[]);self.assertEqual(path.read_bytes(),before)

    def test_terminal_reactivation_invalidates_current_success_without_delivery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=self.fixture(root);host=FakeRunner()
            resume_terminal_closeout(root,path,adapter=host)
            host.config['status']='ACTIVE';host.revision+=1
            for _ in range(2):
                result=resume_terminal_closeout(root,path,adapter=host)
                self.assertEqual(result['status'],'runner_reactivated')
                self.assertFalse(result['completion_claim']);self.assertIsNone(result['receipt'])
                state=load_json_object(path)
                self.assertEqual(state['configured_automation_status'],'ACTIVE')
                self.assertEqual(state['automation']['status'],'ACTIVE')
                self.assertFalse(state['last_automation_pause']['paused'])
                self.assertEqual(state['last_automation_pause']['readback_status'],'ACTIVE')
                self.assertEqual(state['run_count'],2)
            self.assertEqual(len(host.requests),1)
            host.config['status']='PAUSED';host.revision+=1
            self.assertTrue(resume_terminal_closeout(root,path,adapter=host)['completion_claim'])

    def test_final_prompt_is_distinct_and_alert_corruption_is_repaired(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=self.fixture(root);state=load_json_object(path)
            state['final_deep_review_prompt_file']=state['last_review']['file'];write_json_object(path,state)
            host=FakeRunner();result=resume_terminal_closeout(root,path,adapter=host)
            self.assertFalse(result['completion_claim']);self.assertTrue(result['receipt']['paused'])
            state=load_json_object(path);alert=root/state['last_operator_alert']['file'];alert.write_text('partial')
            resume_terminal_closeout(root,path,adapter=host)
            self.assertIn('Next human action:',alert.read_text());self.assertIn('State file:',alert.read_text())
            self.assertEqual(len(list(alert.parent.glob('*.md'))),1)

    def test_failed_initial_readback_retains_specific_pending_outcome(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=self.fixture(root);host=FakeRunner()
            with patch.object(host,'readback',side_effect=OSError('host timeout')):
                result=resume_terminal_closeout(root,path,adapter=host)
            self.assertEqual(result['status'],'transient_failure');self.assertIn('timeout',result['required_action'])
            self.assertFalse(result['completion_claim']);self.assertEqual(host.requests,[])
            self.assertTrue(resume_terminal_closeout(root,path,adapter=host)['completion_claim'])

    def test_validator_requires_receipt_and_detects_reactivation(self):
        from roadmap_delivery.validation import validate_terminal_closeout
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=self.fixture(root);host=FakeRunner();resume_terminal_closeout(root,path,adapter=host)
            state=load_json_object(path);errors=[]
            self.assertTrue(validate_terminal_closeout(state,'PAUSED',errors)['scheduler_pause_confirmed'])
            self.assertEqual(errors,[])
            errors=[];self.assertFalse(validate_terminal_closeout(state,'ACTIVE',errors)['scheduler_pause_confirmed'])
            self.assertEqual(errors[0]['code'],'terminal_runner_reactivated')
            state['terminal_closeout']['receipt']['scheduler_authoritative']=False;errors=[]
            self.assertFalse(validate_terminal_closeout(state,'PAUSED',errors)['scheduler_pause_confirmed'])
            self.assertEqual(errors[0]['code'],'terminal_receipt_unproven')

    def test_missing_status_operation_and_unavailable_readback_are_explicit(self):
        class ReadOnlyHost:
            def readback(self, runner_id): return FakeRunner().readback(runner_id)
        for host in (ReadOnlyHost(), object()):
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);path=self.fixture(root)
                result=resume_terminal_closeout(root,path,adapter=host)
                self.assertEqual(result['status'],'unsupported');self.assertIsNone(result['receipt'])
                self.assertFalse(result['completion_claim']);self.assertEqual(result['attempts'],0)

    def test_final_review_content_must_support_state_verdict(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=self.fixture(root);state=load_json_object(path)
            Path(state['last_review']['file']).write_text('Verdict: needs-fix')
            result=resume_terminal_closeout(root,path,adapter=FakeRunner())
            self.assertTrue(result['receipt']['paused']);self.assertFalse(result['completion_claim'])

    def test_final_verdict_ignores_quotes_and_rejects_ambiguous_metadata(self):
        cases = (
            ("Verdict: needs-fix\nPrevious result was `Verdict: delivered`.\n", False),
            ("Verdict: needs-fix\nVerdict: delivered\n", False),
            ("```text\nVerdict: delivered\n```\n", False),
            ("> Verdict: delivered\n", False),
            ("Verdict: delivered\n```text\nVerdict: needs-fix\n```\n", True),
            ("## Verdict\n\ndelivered\n", True),
        )
        for content, accepted in cases:
            with self.subTest(content=content), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); path = self.fixture(root); host = FakeRunner()
                state = load_json_object(path); Path(state["last_review"]["file"]).write_text(content)
                result = resume_terminal_closeout(root, path, adapter=host)
                self.assertTrue(result["receipt"]["paused"])
                self.assertEqual(result["completion_claim"], accepted)

    def test_unreadable_alert_recovers_and_write_failure_does_not_prevent_pause(self):
        for stalled in (False, True):
            for failure in ("invalid_utf8", "read_denied", "write_denied"):
                with self.subTest(stalled=stalled, failure=failure), tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp); path = self.fixture(root, stalled=stalled); host = FakeRunner()
                    resume_terminal_closeout(root, path)
                    alert = root / load_json_object(path)["last_operator_alert"]["file"]
                    alert.write_bytes(b"\xff\xfe damaged")
                    original = Path.read_text
                    def read(file, *args, **kwargs):
                        if file == alert and failure == "read_denied": raise OSError("alert read denied")
                        return original(file, *args, **kwargs)
                    with patch.object(Path, "read_text", read):
                        if failure == "write_denied":
                            with patch("roadmap_delivery.alerts.atomic_write_text", side_effect=OSError("alert write denied")):
                                result = resume_terminal_closeout(root, path, adapter=host)
                        else:
                            result = resume_terminal_closeout(root, path, adapter=host)
                    self.assertEqual(host.config["status"], "PAUSED")
                    self.assertTrue(result["receipt"]["paused"])
                    self.assertEqual(result["completion_claim"], not stalled and failure != "write_denied")
                    closeout = load_json_object(path)["terminal_closeout"]
                    self.assertIn("Cannot read terminal alert", closeout["alert_recovery_diagnostic"])
                    if failure == "write_denied":
                        self.assertIn("alert write denied", result["required_action"])
                        self.assertTrue(closeout["alert_error"])
                    else:
                        self.assertIn("Next human action:", alert.read_text())


if __name__ == '__main__':
    unittest.main()
