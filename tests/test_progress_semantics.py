import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from roadmap_delivery.control import account_run_outcome, decide_control
from roadmap_delivery.progress import (
    ProgressSignatureError, build_run_result, record_run_result, record_verified_repair, start_run,
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class SemanticFixture:
    def __init__(self, root, threshold=2, **state):
        self.root = Path(root)
        self.directory = self.root / "automation" / "fixture"
        self.directory.mkdir(parents=True)
        self.path = self.directory / "delivery_state.json"
        self.path.write_text(json.dumps({"current_phase": "Phase 2 - Fixture", "status": "blocked",
                                        "run_count": 0, "stalled_run_count": 0,
                                        "blocked_reason": "Missing local artifact", **state}))
        (self.directory / "phase_model_policy.json").write_text(json.dumps({"max_stalled_runs": threshold}))
        self.artifact = self.root / "work.py"
        self.artifact.write_text("accepted implementation\n")
        self.check = self.root / "check.txt"
        self.check.write_text("Required check passed against work.py\n")
        self.review = self.root / "review.md"
        self.review.write_text("Verdict: delivered\nC2-work is accepted against the current artifact.\n")

    def state(self):
        return json.loads(self.path.read_text())

    def start(self, run_id, **kwargs):
        return start_run(self.root, self.path, run_id, owned_files=["work.py"], **kwargs)

    def finish(self, run_id=None, **kwargs):
        return record_run_result(self.root, self.path, run_id=run_id, **kwargs)

    def evidence(self, kind="accepted_phase_work", **overrides):
        item = {"schema_version": 1, "phase": "Phase 2 - Fixture", "kind": kind,
                "criterion_id": "C2-work", "previous": {"status": "unmet"},
                "current": {"status": "accepted", "artifact": "work.py", "artifact_sha256": digest(self.artifact)}}
        if kind == "accepted_phase_work":
            item["increment_id"] = "implementation-1"
        elif kind == "criterion_satisfied":
            item["current"]["status"] = "passed"
        else:
            item.pop("criterion_id")
            item["blocker_id"] = "missing-artifact"
            item["previous"] = {"status": "blocked", "blocked_reason": "Missing local artifact"}
            context = self.state().get("progress_accounting", {}).get("blocker_context") or {}
            if context.get("occurrence_id"):
                item["previous"]["blocker_occurrence_id"] = context["occurrence_id"]
            item["current"]["status"] = "resolved"
        item.update(overrides)
        verifier = self.root / "verifier.json"
        verifier.write_text(json.dumps({"schema_version": 1, "result": "verified", "evidence": [item],
                                        "check": {"path": "check.txt", "sha256": digest(self.check), "result": "passed"},
                                        "review": {"path": "review.md", "sha256": digest(self.review)}}))
        return [{**item, "verifier": {"path": "verifier.json", "sha256": digest(verifier)}}]


class ProgressSemanticsTests(unittest.TestCase):
    def test_blocker_discovered_at_threshold_has_new_identity_for_each_occurrence(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = SemanticFixture(tmp, status="not_started", blocked_reason=None)
            occurrences = []
            old = None
            for cycle in (1, 2):
                for attempt in (1, 2):
                    run_id = f"cycle-{cycle}-attempt-{attempt}"
                    f.start(run_id)
                    if attempt == 2:
                        state = f.state(); state.update(status="blocked", blocked_reason="Missing local artifact")
                        f.path.write_text(json.dumps(state))
                    f.finish(run_id)
                occurrences.append(f.state()["progress_accounting"]["blocker_context"]["occurrence_id"])
                if old:
                    with self.assertRaisesRegex(ProgressSignatureError, "current blocker occurrence"):
                        record_verified_repair(f.root, f.path, old)
                fresh = f.evidence("blocker_resolved")
                result = record_verified_repair(f.root, f.path, fresh)
                self.assertTrue(result["recorded"]); self.assertFalse(result["duplicate"])
                self.assertEqual((f.state()["run_count"], f.state()["stalled_run_count"]), (cycle * 2, 0))
                old = fresh
            self.assertNotEqual(*occurrences)

    def test_quoted_delivered_verdict_cannot_attest_accepted_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = SemanticFixture(tmp); f.start("review-quote")
            f.review.write_text("Verdict: needs-fix\nC2-work previously had `Verdict: delivered`.\n")
            with self.assertRaisesRegex(ProgressSignatureError, "delivered review"):
                f.finish("review-quote", semantic_evidence=f.evidence())

    def test_persistent_completion_cannot_be_reopened_by_recovery_or_repair(self):
        for marker in ({"status": "completed_pending_pause"}, {"all_phases_complete": True}):
            for repair in (False, True):
                with self.subTest(marker=marker, repair=repair), tempfile.TemporaryDirectory() as tmp:
                    f = SemanticFixture(tmp, 1); f.start("unfinished")
                    evidence = f.evidence("blocker_resolved") if repair else []
                    state = f.state(); state.update(marker); f.path.write_text(json.dumps(state))
                    before = f.path.read_bytes()
                    with self.assertRaisesRegex(ProgressSignatureError, "Completed scope"):
                        f.finish("unfinished", outcome="interrupted", semantic_evidence=evidence)
                    with self.assertRaisesRegex(ProgressSignatureError, "Completed scope"):
                        f.start("unfinished")
                    with self.assertRaisesRegex(ValueError, "Completed scope"):
                        account_run_outcome(state, {})
                    self.assertEqual(f.path.read_bytes(), before)

    def test_pending_journal_cannot_overwrite_newer_completion(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = SemanticFixture(tmp, 1); f.start("unfinished")
            with patch("roadmap_delivery.progress.write_progress_json_object", side_effect=ProgressSignatureError("crash")):
                with self.assertRaises(ProgressSignatureError): f.finish("unfinished")
            state = f.state(); state["status"] = "completed_pending_pause"; f.path.write_text(json.dumps(state))
            before = f.path.read_bytes()
            with self.assertRaisesRegex(ProgressSignatureError, "Completed scope"):
                f.finish("unfinished", outcome="interrupted")
            self.assertEqual(f.path.read_bytes(), before)

    def test_same_cause_recurrence_needs_new_occurrence_bound_repair(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = SemanticFixture(tmp)
            for run in ("one", "two"): f.start(run); f.finish(run)
            old = f.evidence("blocker_resolved")
            record_verified_repair(f.root, f.path, old)
            state = f.state(); state.update(status="blocked", blocked_reason="Missing local artifact")
            f.path.write_text(json.dumps(state))
            for run in ("three", "four"): f.start(run); f.finish(run)
            with self.assertRaisesRegex(ProgressSignatureError, "current blocker occurrence"):
                record_verified_repair(f.root, f.path, old)
            fresh = f.evidence("blocker_resolved")
            result = record_verified_repair(f.root, f.path, fresh)
            self.assertFalse(result["duplicate"])
            self.assertEqual((f.state()["run_count"], f.state()["stalled_run_count"]), (4, 0))
            self.assertIsNone(f.state()["blocked_reason"])
            self.assertTrue(record_verified_repair(f.root, f.path, fresh)["duplicate"])

    def test_exact_boundaries_and_ten_attempts_cannot_evade_terminal_stop(self):
        for threshold in (1, 2, 3):
            with self.subTest(threshold=threshold), tempfile.TemporaryDirectory() as tmp:
                f = SemanticFixture(tmp, threshold)
                for n in range(1, 11):
                    # Fresh activity and failure wording never change evidence.
                    (f.directory / "delivery_log.md").write_text(f"activity {n}\n")
                    f.review.write_text(f"Verdict: delivered\nrepeated review {n}\n")
                    s = f.state()
                    s.update(last_review={"file": f"review-{n}.md", "verdict": "delivered"},
                             last_verification={"status": "passed", "verified_at": f"time-{n}"},
                             git_head=f"bookkeeping-commit-{n}", updated_at=f"time-{n}")
                    f.path.write_text(json.dumps(s))
                    if n > threshold:
                        with self.assertRaisesRegex(ProgressSignatureError, "terminal reconciliation"):
                            f.start(f"run-{n}")
                        self.assertEqual(f.state()["run_count"], threshold)
                        continue
                    f.start(f"run-{n}")
                    # Rewording the error after start cannot discard the original cause.
                    s = f.state(); s["blocked_reason"] = f"Missing artifact, retry wording {n}"; f.path.write_text(json.dumps(s))
                    result = f.finish(f"run-{n}")
                    self.assertFalse(result["progress_detected"])
                    self.assertEqual(result["stalled_run_count"], n)
                    self.assertEqual(result["threshold_reached"], n == threshold)
                    if n == threshold:
                        self.assertFalse(result["terminal_plan"]["extract_phase"])
                        self.assertEqual(result["terminal_plan"]["stage"], "terminal_reconciliation")
                        self.assertEqual(f.state()["blocked_reason"], "Missing local artifact")

    def test_ten_real_bookkeeping_commits_and_repeated_reviews_do_not_reopen_stop(self):
        import subprocess
        with tempfile.TemporaryDirectory() as tmp:
            f=SemanticFixture(tmp)
            def git(*args):
                return subprocess.run(["git", "-C", str(f.root), *args], check=True,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            git("init", "-q")
            for n in range(1, 11):
                log=f.directory / "delivery_log.md"; log.write_text(f"routine activity {n}\n")
                git("add", "automation/fixture/delivery_log.md")
                git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-q", "-m", f"bookkeeping {n}")
                f.review.write_text(f"Verdict: delivered\nRepeated review {n}\n")
                if n <= 2:
                    f.start(str(n)); r=f.finish(str(n))
                else:
                    with self.assertRaisesRegex(ProgressSignatureError, "terminal reconciliation"): f.start(str(n))
                    r=f.finish("2")
                self.assertFalse(r["progress_detected"])
                self.assertEqual(f.state()["stalled_run_count"], min(n, 2))
                self.assertEqual(f.state()["blocked_reason"], "Missing local artifact")
            self.assertEqual(git("rev-list", "--count", "HEAD").stdout.strip(), "10")

    def test_first_missing_signature_is_failure_and_preview_allocates_no_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = SemanticFixture(tmp)
            before = f.path.read_bytes()
            preview = build_run_result(f.root, f.path)
            self.assertEqual(preview["run_count"], 0)
            self.assertTrue(preview["outcome_pending"])
            self.assertEqual(before, f.path.read_bytes())
            f.start("first")
            self.assertEqual(f.finish("first")["stalled_run_count"], 1)

    def test_accepted_work_deduplicates_increment_and_revision_across_run_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = SemanticFixture(tmp, 10)
            f.start("one")
            self.assertTrue(f.finish("one", semantic_evidence=f.evidence())["progress_detected"])
            for n in range(2, 5):
                f.start(str(n))
                # New ID and proof filename cannot turn the same artifact into work.
                self.assertFalse(f.finish(str(n), semantic_evidence=f.evidence(increment_id=f"claim-{n}"))["progress_detected"])
            f.artifact.write_text("second accepted implementation\n")
            f.start("five")
            # A different hash alone with the same semantic increment is also activity.
            self.assertFalse(f.finish("five", semantic_evidence=f.evidence())["progress_detected"])
            f.start("six")
            self.assertTrue(f.finish("six", semantic_evidence=f.evidence(increment_id="implementation-2"))["progress_detected"])
            self.assertEqual(f.state()["stalled_run_count"], 0)

    def test_newly_satisfied_check_counts_once_even_with_new_artifact_and_proof(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = SemanticFixture(tmp, 4)
            f.start("first")
            self.assertTrue(f.finish("first", semantic_evidence=f.evidence("criterion_satisfied"))["progress_detected"])
            f.artifact.write_text("new revision with repeated passing criterion\n")
            f.start("second")
            r = f.finish("second", semantic_evidence=f.evidence("criterion_satisfied"))
            self.assertFalse(r["progress_detected"])
            self.assertEqual(r["stalled_run_count"], 1)

    def test_one_verified_repair_resets_once_and_clears_only_original_cause(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = SemanticFixture(tmp, 4)
            f.start("first"); f.finish("first")
            f.start("repair")
            evidence = f.evidence("blocker_resolved")
            result = f.finish("repair", semantic_evidence=evidence)
            self.assertTrue(result["progress_detected"])
            self.assertEqual(f.state()["stalled_run_count"], 0)
            self.assertIsNone(f.state()["blocked_reason"])
            before = f.path.read_bytes()
            duplicate = f.finish("repair", semantic_evidence=evidence)
            self.assertTrue(duplicate["duplicate"])
            self.assertEqual(duplicate["run_count"], 2)
            self.assertEqual(before, f.path.read_bytes())
            f.start("repeat")
            with self.assertRaisesRegex(ProgressSignatureError, "original actionable"):
                f.finish("repeat", semantic_evidence=f.evidence("blocker_resolved"))
            self.assertEqual(f.finish("repeat")["stalled_run_count"], 1)

    def test_rejects_claims_changed_hashes_wrong_review_and_wrong_blocker(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = SemanticFixture(tmp, 10); f.start("first")
            bad = [f.evidence()[0]]; bad[0].pop("verifier")
            with self.assertRaises(ProgressSignatureError): f.finish("first", semantic_evidence=bad)
            evidence = f.evidence(); f.artifact.write_text("changed after verification\n")
            with self.assertRaisesRegex(ProgressSignatureError, "changed evidence"): f.finish("first", semantic_evidence=evidence)
            f.review.write_text("Verdict: needs-fix\nC2-work\n")
            with self.assertRaisesRegex(ProgressSignatureError, "delivered review"): f.finish("first", semantic_evidence=f.evidence())
            with self.assertRaisesRegex(ProgressSignatureError, "newly satisfied"):
                f.finish("first", semantic_evidence=f.evidence(previous={"status": "passed"}))
            with self.assertRaisesRegex(ProgressSignatureError, "original actionable"):
                f.finish("first", semantic_evidence=f.evidence("blocker_resolved", previous={"status": "blocked", "blocked_reason": "Different cause"}))
            self.assertEqual(f.state()["run_count"], 0)

    def test_duplicate_start_outcome_and_conflicting_id_revision_are_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = SemanticFixture(tmp, 4)
            f.start("one")
            self.assertTrue(f.start("one")["duplicate"])
            with self.assertRaisesRegex(ProgressSignatureError, "unfinished"): f.start("two")
            with self.assertRaisesRegex(ProgressSignatureError, "revision"): f.finish("one", expected_revision=0)
            first = f.finish("one")
            duplicate = f.finish("one", timestamp="later")
            self.assertTrue(duplicate["duplicate"])
            self.assertEqual(duplicate["timestamp"], first["timestamp"])
            self.assertEqual(f.state()["run_count"], 1)
            with self.assertRaisesRegex(ProgressSignatureError, "already completed"): f.start("one")
            self.assertEqual(len((f.directory / "automation_run_log.jsonl").read_text().splitlines()), 2)

    def test_interrupted_outcome_recovery_with_and_without_progress(self):
        for progress in (False, True):
            with self.subTest(progress=progress), tempfile.TemporaryDirectory() as tmp:
                f = SemanticFixture(tmp, 4); f.start("interrupted")
                r = f.finish(outcome="interrupted", semantic_evidence=f.evidence() if progress else [])
                self.assertEqual(r["stalled_run_count"], 0 if progress else 1)
                self.assertEqual(f.state()["run_count"], 1)
                self.assertTrue(f.finish("interrupted", outcome="interrupted")["duplicate"])

    def test_write_ahead_start_and_outcome_recover_after_state_failure(self):
        for stage in ("start", "outcome"):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as tmp:
                f = SemanticFixture(tmp, 4)
                if stage == "outcome": f.start("one")
                with patch("roadmap_delivery.progress.write_progress_json_object", side_effect=ProgressSignatureError("interrupted replace")):
                    with self.assertRaisesRegex(ProgressSignatureError, "interrupted replace"):
                        f.start("one") if stage == "start" else f.finish("one")
                r = f.start("one") if stage == "start" else f.finish("one")
                self.assertTrue(r["duplicate"])
                if stage == "start": f.finish("one")
                self.assertEqual(f.state()["run_count"], 1)
                self.assertEqual(f.state()["stalled_run_count"], 1)

    def test_failed_journal_write_does_not_update_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = SemanticFixture(tmp, 4); f.start("one"); before = f.path.read_bytes()
            with patch("roadmap_delivery.progress.append_run_log", side_effect=ProgressSignatureError("disk full")):
                with self.assertRaises(ProgressSignatureError): f.finish("one")
            self.assertEqual(before, f.path.read_bytes())
            self.assertEqual(f.finish("one")["run_count"], 1)

    def test_legacy_migration_preserves_failures_and_marks_uncertainty(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = SemanticFixture(tmp, 3, run_count=5, stalled_run_count=2, last_progress_signature="sha256:old")
            f.start("new"); r = f.finish("new")
            self.assertEqual((r["run_count"], r["stalled_run_count"]), (6, 3))
            self.assertTrue(r["threshold_reached"])
            migration = f.state()["progress_accounting"]["migration"]
            self.assertTrue(migration["uncertain_history"])
            self.assertEqual(migration["baseline_stalled_run_count"], 2)
            self.assertEqual(f.state()["last_progress_signature"], "sha256:old")

    def test_latest_legacy_failure_counter_conflict_stops_without_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            f=SemanticFixture(tmp, 2, run_count=5, stalled_run_count=0)
            entry={"timestamp":"recorded", "current_phase":"Phase 2 - Fixture", "status":"blocked",
                   "progress_signature":"sha256:legacy", "run_count":5, "stalled_run_count":2,
                   "max_stalled_runs":2, "threshold_reached":True, "phase_6_alert_required":True}
            log=f.directory / "automation_run_log.jsonl"; log.write_text(json.dumps(entry)+"\n")
            before=(f.path.read_bytes(),log.read_bytes())
            with self.assertRaisesRegex(ProgressSignatureError,"more known consecutive failures"):
                f.start("new")
            self.assertEqual((f.path.read_bytes(),log.read_bytes()),before)

    def test_latest_accepted_legacy_repair_can_legitimately_lower_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            f=SemanticFixture(tmp, 2, run_count=6, stalled_run_count=0)
            failure={"run_count":5,"stalled_run_count":2,"progress_signature":"sha256:legacy"}
            repair={"run_id":"accepted-bootstrap-repair", "phase":"Phase 2 - Fixture", "run_count":6,
                    "stalled_run_count":0, "semantic_progress_evidence":[{"criterion_id":"original-cause-repair", "artifact_sha256":digest(f.artifact)}]}
            (f.directory / "automation_run_log.jsonl").write_text(json.dumps(failure)+"\n"+json.dumps(repair)+"\n")
            f.start("new"); result=f.finish("new")
            self.assertEqual((result["run_count"],result["stalled_run_count"]),(7,1))
            self.assertFalse(result["progress_detected"])

    def test_malformed_or_conflicting_history_never_overwrites_counters(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = SemanticFixture(tmp, 4); f.start("one"); f.finish("one")
            s = f.state(); s["run_count"] = 0; f.path.write_text(json.dumps(s)); before=f.path.read_bytes()
            with self.assertRaisesRegex(ProgressSignatureError, "conflict"): f.start("two")
            self.assertEqual(before, f.path.read_bytes())
            (f.directory / "automation_run_log.jsonl").write_text('{"run_count": 10}\n')
            s.pop("progress_accounting"); s["stalled_run_count"] = 0; f.path.write_text(json.dumps(s))
            with self.assertRaisesRegex(ProgressSignatureError, "more known runs"): f.start("two")

    def test_threshold_repair_resets_once_without_new_attempt_or_lifetime_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            f=SemanticFixture(tmp)
            f.start("one"); f.finish("one")
            f.start("two"); f.finish("two")
            evidence=f.evidence("blocker_resolved")
            result=record_verified_repair(f.root, f.path, evidence)
            self.assertTrue(result["progress_detected"])
            self.assertEqual((f.state()["run_count"], f.state()["stalled_run_count"]), (2, 0))
            self.assertIsNone(f.state()["blocked_reason"])
            f.start("three"); f.finish("three")
            duplicate=record_verified_repair(f.root, f.path, evidence)
            self.assertTrue(duplicate["duplicate"])
            self.assertFalse(duplicate["progress_detected"])
            self.assertEqual((duplicate["run_count"], duplicate["stalled_run_count"]), (3, 1))
            self.assertEqual(duplicate["proposed_state_changes"], {})
            self.assertEqual((f.state()["run_count"], f.state()["stalled_run_count"]), (3, 1))

    def test_malformed_empty_evidence_and_journal_outcomes_fail_safely(self):
        with tempfile.TemporaryDirectory() as tmp:
            f=SemanticFixture(tmp); f.start("one")
            for malformed in ({}, False, "claim"):
                with self.assertRaises(ProgressSignatureError): f.finish("one", semantic_evidence=malformed)
            f.finish("one")
            log=f.directory / "automation_run_log.jsonl"
            entries=[json.loads(line) for line in log.read_text().splitlines()]
            entries[-1].pop("result")
            log.write_text("\n".join(json.dumps(e) for e in entries)+"\n")
            with self.assertRaisesRegex(ProgressSignatureError, "journal outcome"): f.finish("one")

    def test_bootstrap_evidence_is_consumed_by_migration_without_new_progress(self):
        with tempfile.TemporaryDirectory() as tmp:
            f=SemanticFixture(tmp, 4, run_count=1)
            entry={"run_id":"bootstrap", "phase":"Phase 2 - Fixture", "run_count":1,
                   "semantic_progress_evidence":[{"criterion_id":"C2-work", "artifact_sha256":digest(f.artifact)}]}
            (f.directory / "automation_run_log.jsonl").write_text(json.dumps(entry)+"\n")
            f.start("new")
            self.assertFalse(f.finish("new", semantic_evidence=f.evidence())["progress_detected"])
            self.assertEqual(f.state()["run_count"], 2)
            self.assertFalse(f.state()["progress_accounting"]["migration"]["uncertain_history"])

    def test_record_outcome_applies_terminal_priority_to_updated_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = SemanticFixture(tmp, 1); f.start("one")
            s=f.state()
            evidence={"run_evidence": {"run_id": "one", "validated": True, "items": [], "outcome": "completed"}}
            plan = decide_control(s, evidence=evidence, event="record_outcome")
            self.assertEqual(plan["stage"], "terminal_reconciliation")
            self.assertEqual(plan["proposed_state_changes"]["run_count"], 1)
            self.assertEqual(plan["proposed_state_changes"]["blocked_reason"], "Missing local artifact")
            self.assertFalse(plan["extract_phase"])
            self.assertEqual(s["run_count"], 0)

    def test_lock_conflict_stops_without_overwriting_state(self):
        import fcntl
        with tempfile.TemporaryDirectory() as tmp:
            f=SemanticFixture(tmp); before=f.path.read_bytes()
            with (f.directory / ".progress.lock").open("a") as lock:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                with self.assertRaisesRegex(ProgressSignatureError, "Another writer"): f.start("one")
            self.assertEqual(before, f.path.read_bytes())

    def test_completed_marker_wins_over_outcome_and_repair_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            f=SemanticFixture(tmp); f.start("one")
            state=f.state(); state.update(status="completed_pending_pause", all_phases_complete=True)
            for event in ("record_outcome", "recover_run", "operator_resume"):
                evidence={"run_evidence":{"run_id":"one", "validated":True, "items":[], "outcome":"completed"},
                          "verified_repair": {"run_id":"repair", "validated":True, "items":[], "outcome":"completed"}}
                plan=decide_control(state, evidence=evidence, event=event)
                self.assertEqual(plan["stage"], "terminal_reconciliation")
                self.assertNotIn("run_count", plan["proposed_state_changes"])
                self.assertFalse(plan["extract_phase"])

    def test_journal_schema_rejects_missing_outcome_and_duplicate_event_keys(self):
        from roadmap_delivery.validation import validate_json_schema
        schema=json.loads((Path(__file__).resolve().parents[1] / "schemas/automation_run_log.schema.json").read_text())
        with tempfile.TemporaryDirectory() as tmp:
            f=SemanticFixture(tmp); f.start("one"); f.finish("one")
            entries=[json.loads(line) for line in (f.directory / "automation_run_log.jsonl").read_text().splitlines()]
            for entry in entries:
                self.assertEqual(validate_json_schema(entry, schema), [])
            invalid=json.loads(json.dumps(entries[-1])); invalid.pop("result")
            self.assertTrue(validate_json_schema(invalid, schema))
            invalid=json.loads(json.dumps(entries[-1])); invalid["state_changes"]["progress_accounting"]["consumed_events"]=["duplicate","duplicate"]
            self.assertTrue(validate_json_schema(invalid, schema))

    def test_terminal_scope_does_not_allocate_an_attempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            f=SemanticFixture(tmp, status="completed_pending_pause", all_phases_complete=True)
            with self.assertRaisesRegex(ProgressSignatureError, "Completed scope"): f.start("one")
            self.assertEqual(f.state()["run_count"], 0)


if __name__ == "__main__":
    unittest.main()
