"""Offline runner contracts; every config lives in an isolated temporary root."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from roadmap_delivery.automation import (
    FileRunnerAdapter, RunnerError, config_revision, pause_saved_automation,
    prepare_pause_request, runner_snapshot, verify_pause_receipt,
)
from roadmap_delivery.toml import TomlError, parse_toml


CONFIG = {
    "id": "fixture", "status": "ACTIVE", "prompt": 'Use state first.\nstatus = "ACTIVE"\nKeep the prompt.',
    "model": "fixture-model", "reasoning_effort": "low", "rrule": "FREQ=HOURLY",
    "cwds": ["/isolated/repo"], "target": {"type": "project", "project_id": "fixture-project"},
    "execution_environment": "local", "notificationPolicy": "failed_runs_only",
    "unknown": {"keep": [True, 2, "value"]}, "updated_at": 1,
}


class FakeRunner:
    """Observable CAS/idempotency host; never consults the user's scheduler."""
    def __init__(self, config=None):
        self.config = copy.deepcopy(CONFIG if config is None else config)
        self.revision = 1
        self.requests = []
        self.reads = 0
        self.applied = set()
        self.reject = None
        self.leave_active = False
        self.change_setting = False
        self.lose_ack = False

    def readback(self, automation_id):
        self.reads += 1
        return runner_snapshot(self.config, source="isolated fake host", revision=str(self.revision))

    def pause_status_only(self, request):
        if request["request_id"] in self.applied:
            return
        if request["expected_revision"] != str(self.revision):
            raise RunnerError("stale_revision", "Fake host rejected stale revision.")
        self.requests.append(copy.deepcopy(request))
        if self.reject:
            raise self.reject
        if self.leave_active:
            return
        self.config = copy.deepcopy(request["payload"])
        self.config["updated_at"] += 1
        if self.change_setting:
            self.config["model"] = "other-model"
        self.revision += 1
        self.applied.add(request["request_id"])
        if self.lose_ack:
            raise OSError("Ack lost after successful update.")


class RunnerUpdateTests(unittest.TestCase):
    def test_supported_adapter_preserves_full_payload_and_requires_readback(self):
        host = FakeRunner()
        before = copy.deepcopy(host.config)
        result = pause_saved_automation("fixture", adapter=host, expected={"id": "fixture", "target": CONFIG["target"]})
        self.assertTrue(result["paused"])
        self.assertTrue(result["scheduler_authoritative"])
        self.assertEqual(host.reads, 2)
        self.assertEqual(host.requests[0]["payload"], {**before, "status": "PAUSED"})
        self.assertEqual({k:v for k,v in host.config.items() if k not in {"status", "updated_at"}}, {k:v for k,v in before.items() if k not in {"status", "updated_at"}})

    def test_update_ack_alone_and_wrong_identity_never_claim_pause(self):
        for modification, status in (("leave_active", "pause_unconfirmed"), ("change_setting", "settings_changed")):
            host = FakeRunner(); setattr(host, modification, True)
            result = pause_saved_automation("fixture", adapter=host)
            self.assertFalse(result["paused"])
            self.assertEqual(result["status"], status)
        for expected in ({"id": "wrong"}, {"id": "fixture", "target": {"project_id": "other"}}):
            host = FakeRunner()
            result = pause_saved_automation("fixture", adapter=host, expected=expected)
            self.assertFalse(result["paused"])
            self.assertEqual(host.requests, [])

    def test_unavailable_file_contract_does_not_even_read_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = pause_saved_automation("fixture", root=root)
            self.assertEqual(result["status"], "unsupported")
            self.assertFalse(result["attempted"])
            self.assertEqual(list(root.iterdir()), [])

    def test_revision_and_capability_are_required(self):
        host = FakeRunner()
        result = pause_saved_automation("fixture", adapter=host, expected_revision="old")
        self.assertEqual(result["status"], "stale_revision")
        self.assertEqual(host.requests, [])
        for changes in ({"revision": None}, {"scheduler_authoritative": False}, {"source": ""}):
            snapshot = {**host.readback("fixture"), **changes}
            with self.assertRaises(RunnerError):
                prepare_pause_request(snapshot, {"id": "fixture"}, "request")

    def test_real_parser_preserves_tables_inline_comments_and_status_prompt_text(self):
        text = '''id = "fixture"
status = "ACTIVE" # enabled by operator
prompt = """Do not change this.
status = "ACTIVE"
"""
cwds = ["/repo"]
[notification]
status = "custom"
quiet = true
[[events]]
name = "one"
[[events]]
name = "two"
'''
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); path = root / "fixture" / "automation.toml"; path.parent.mkdir()
            path.write_text(text); path.chmod(0o640)
            original = parse_toml(text)
            result = pause_saved_automation("fixture", root=root, host_contract="fixture file scheduler contract")
            self.assertTrue(result["paused"])
            self.assertEqual(parse_toml(path.read_text()), {**original, "status": "PAUSED"})
            self.assertEqual(path.stat().st_mode & 0o777, 0o640)
            again = pause_saved_automation("fixture", root=root, host_contract="fixture file scheduler contract")
            self.assertEqual(again["status"], "already_paused")
            self.assertFalse(again["attempted"])

    def test_malformed_readonly_and_atomic_write_failures_preserve_original(self):
        for text, readonly, mocked in (('id="fixture"\nstatus="ACTIVE"\nstatus="PAUSED"\n', False, False), ('id="fixture"\nstatus="ACTIVE"\n', True, False), ('id="fixture"\nstatus="ACTIVE"\n', False, True)):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); path = root / "fixture" / "automation.toml"; path.parent.mkdir(); path.write_text(text)
                if readonly: path.chmod(0o444)
                if mocked:
                    with patch("roadmap_delivery.state.os.replace", side_effect=OSError("disk failure")):
                        result = pause_saved_automation("fixture", root=root, host_contract="fixture")
                else:
                    result = pause_saved_automation("fixture", root=root, host_contract="fixture")
                self.assertFalse(result["paused"])
                self.assertEqual(path.read_text(), text)
                self.assertFalse(any(p.name.startswith('.automation.toml') for p in path.parent.iterdir()))

    def test_file_cas_rejects_concurrent_change_and_idempotent_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); path = root / "fixture" / "automation.toml"; path.parent.mkdir(); path.write_text('id="fixture"\nstatus="ACTIVE"\nprompt="keep"\n')
            backend = FileRunnerAdapter(root, host_contract="isolated authoritative file")
            request = prepare_pause_request(backend.readback("fixture"), {"id":"fixture"}, "run-1")
            original = path.read_text(); path.write_text(original+'other=1\n')
            with self.assertRaisesRegex(RunnerError, "changed"):
                backend.pause_status_only(request)
            self.assertEqual(path.read_text(), original+'other=1\n')
            request = prepare_pause_request(backend.readback("fixture"), {"id":"fixture"}, "run-1")
            backend.pause_status_only(request); after = path.read_bytes(); backend.pause_status_only(request)
            self.assertEqual(path.read_bytes(), after)
            self.assertTrue(verify_pause_receipt(backend.readback("fixture"), {"id":"fixture"}, request)["paused"])

    def test_path_escape_and_symlink_stop_without_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = root / "outside.toml"; source.write_text('id="fixture"\nstatus="ACTIVE"\n')
            (root / "fixture").mkdir(); (root / "fixture" / "automation.toml").symlink_to(source)
            result = pause_saved_automation("fixture", root=root, host_contract="fixture")
            self.assertEqual(result["status"], "unsafe_path")
            result = pause_saved_automation("../outside", root=root, host_contract="fixture")
            self.assertFalse(result["paused"])
            self.assertEqual(source.read_text(), 'id="fixture"\nstatus="ACTIVE"\n')

    def test_parser_handles_whole_document_and_rejects_duplicates(self):
        self.assertEqual(parse_toml('target={type="project", project_id="p"}\n')["target"]["project_id"], "p")
        with self.assertRaises(TomlError): parse_toml('status="ACTIVE"\nstatus="PAUSED"\n')


if __name__ == "__main__":
    unittest.main()
