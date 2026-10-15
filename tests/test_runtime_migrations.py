"""Offline upgrade/rollback scenarios; no real automation configuration."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
import shutil
import subprocess
import sys
from unittest.mock import patch

from roadmap_delivery.approval import default_approval_policy
from roadmap_delivery.automation import RunnerError, runner_snapshot
from roadmap_delivery.control import decide_control
from roadmap_delivery.migrations import (
    LEGACY_PROMPTS, VERSIONS, digest, plan_migration, record_verified_migration,
    remember_decision, render_prompt, resume_migration, rollback_plan, validate_plan,
)
from roadmap_delivery.state import load_json_object, write_json_object

SLUG = "fixture"
ROADMAP = "roadmaps/not_started_fixture.md"
POLICY = default_approval_policy("conservative")
CONFIG = {"id": "fixture", "status": "ACTIVE", "prompt": render_prompt(SLUG, LEGACY_PROMPTS["9c0d7ae^"], roadmap=ROADMAP),
          "cwds": ["/isolated/repo"], "target": {"type": "project", "project_id": "fixture-project"},
          "execution_environment": "local", "model": "fixture-model", "reasoning_effort": "xhigh",
          "rrule": "FREQ=HOURLY", "notificationPolicy": "failed_runs_only", "unknown": {"keep": [1, True]}}
EXPECTED = {k: CONFIG[k] for k in ("id", "cwds", "target", "execution_environment")}


class FakeMigrationRunner:
    def __init__(self, config=None):
        self.config = copy.deepcopy(config or CONFIG)
        self.revision = 1
        self.requests = []
        self.applied = set()
        self.ack_lost = False
        self.ignore = False
        self.concurrent = False
        self.corrupt_settings = False

    def readback(self, runner_id):
        return runner_snapshot(self.config, source="offline fake host", revision=str(self.revision))

    def update_prompt_only(self, request):
        if request["request_id"] in self.applied:
            return
        self.requests.append(copy.deepcopy(request))
        if self.concurrent:
            self.revision += 1
            self.config["prompt"] += " Human edit."
        if request["expected_revision"] != str(self.revision):
            raise RunnerError("stale_revision", "CAS rejected concurrent edit.")
        if self.ignore:
            return
        self.config = copy.deepcopy(request["payload"])
        if self.corrupt_settings:
            self.config["model"] = "unexpected"
        self.revision += 1
        self.applied.add(request["request_id"])
        if self.ack_lost:
            raise OSError("Lost host acknowledgement after applied effect.")


def build(host, policy=POLICY, policy_path=None):
    return plan_migration(host.readback("fixture"), EXPECTED, SLUG, policy, roadmap=ROADMAP, policy_path=policy_path)


def auth(plan, direction="forward"):
    return {"authorized": True, "runner_id": "fixture", "plan_id": plan["plan_id"],
            "direction": direction, "effects": plan["effects"], "source": "fixture operator setup/session authorization"}


class MigrationTests(unittest.TestCase):
    def build(self, host, policy=POLICY, policy_path=None):
        return build(host, policy, str(self.policy) if policy_path is None else policy_path)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.policy = self.root / "approval_policy.json"
        self.journal = self.root / "migration_receipts.json"
        write_json_object(self.policy, POLICY)

    def apply(self, host, plan=None, authority=True, direction="forward"):
        plan = plan or self.build(host)
        return resume_migration(plan, self.journal, adapter=host,
                                authority=auth(plan, direction) if authority is True else authority,
                                policy_path=self.policy, direction=direction)

    def test_exact_frozen_legacy_versions_and_literal_path_upgrade(self):
        fixture_root = Path(__file__).parent / "fixtures/runtime-reliability/migrations"
        for rev, text in LEGACY_PROMPTS.items():
            with self.subTest(rev=rev):
                self.assertEqual((fixture_root/(rev.replace("^", "-parent")+".txt")).read_text(), text+"\n")
                host = FakeMigrationRunner({**CONFIG, "prompt": render_prompt(SLUG, text, roadmap=ROADMAP)})
                before = copy.deepcopy(host.config)
                plan = self.build(host)
                self.assertEqual(plan["status"], "planned")
                self.assertEqual(plan["provenance"]["prompt_source"], rev)
                self.assertIn("before/prompt", plan["diffs"]["prompt"])
                self.assertEqual(host.requests, [])
                result = self.apply(host, plan)
                self.assertEqual(result["status"], "verified")
                self.assertEqual(host.config, {**before, "prompt": render_prompt(SLUG)})
                self.assertIn("state roadmap field is authoritative", host.config["prompt"])
                self.assertIn("explicitly\nfalse", host.config["prompt"])
                self.assertEqual(result["receipt"]["versions"], VERSIONS)
                count = len(host.requests)
                saved = self.journal.read_bytes()
                self.assertEqual(self.apply(host, plan)["status"], "verified")
                self.assertEqual(self.journal.read_bytes(), saved)
                self.assertEqual(len(host.requests), count)
                self.assertEqual(self.build(host)["effects"], [])

    def test_missing_malformed_unknown_and_custom_text_need_decision_without_rewrite(self):
        for policy in (None, [], {"approval_mode": "surprise"}, {**POLICY, "pause_automation_on_stall": "false"}):
            plan = self.build(FakeMigrationRunner(), policy)
            self.assertEqual(plan["status"], "needs-decision")
            self.assertEqual(plan["effects"], [])
        for text in ("Human-owned prompt", CONFIG["prompt"]+"\nNever edit my saved prompt."):
            host = FakeMigrationRunner({**CONFIG, "prompt": text})
            plan = self.build(host)
            self.assertIn("unknown_prompt_provenance", plan["issues"])
            self.assertEqual(plan["after"], host.config)
            with self.assertRaises(RunnerError):
                self.apply(host, plan)
            self.assertEqual(host.requests, [])

    def test_custom_restrictions_explicit_optouts_and_history_preserved(self):
        custom = {**POLICY, "pause_automation_on_completion": False, "pause_automation_on_stall": False,
                  "operator_note": "Never promote my branches"}
        write_json_object(self.policy, custom)
        host = FakeMigrationRunner(); plan = self.build(host, custom)
        self.assertEqual(plan["after_policy"], custom)
        result = self.apply(host, plan)
        self.assertEqual(result["status"], "verified")
        self.assertEqual(load_json_object(self.policy), custom)
        old = {"configured_automation_model": None, "configured_automation_status": None,
               "migration_history": [{"plan_id": "old", "direction": "forward"}], "run_count": 42}
        state = record_verified_migration(old, plan, result)
        self.assertEqual(state["configured_automation_model"], None)
        self.assertEqual(state["configured_automation_status"], None)
        self.assertEqual(state["migration_history"][0], old["migration_history"][0])
        self.assertEqual(state["run_count"], 42)
        self.assertEqual(record_verified_migration(state, plan, result), state)

    def test_known_policy_defaults_upgrade_is_explicit_and_resumable(self):
        legacy = {k:v for k,v in POLICY.items() if not k.startswith("pause_automation_on_")}
        write_json_object(self.policy, legacy)
        host = FakeMigrationRunner(); plan = self.build(host, legacy, policy_path=str(self.policy))
        self.assertIn("write_policy", plan["effects"])
        with patch("roadmap_delivery.migrations.write_json_object", side_effect=lambda path, value: (_ for _ in ()).throw(OSError("policy write interrupted")) if path == self.policy else write_json_object(path, value)):
            partial = self.apply(host, plan)
        self.assertEqual(partial["status"], "applied")
        self.assertIsNone(partial["receipt"])
        self.assertEqual(len(host.requests), 1)
        result = self.apply(host, plan)
        self.assertEqual(result["status"], "verified")
        self.assertEqual(load_json_object(self.policy), POLICY)
        self.assertEqual(len(host.requests), 1)

    def test_scoped_authorization_reused_but_not_inferred_from_skill_or_pause(self):
        host = FakeMigrationRunner(); plan = self.build(host)
        for authority in (None, {**auth(plan), "runner_id": "other"}, {**auth(plan), "plan_id": "other"},
                          {**auth(plan), "effects": ["pause_status_only"]}, {**auth(plan), "direction": "rollback"},
                          {**auth(plan), "source": None}):
            self.assertEqual(self.apply(host, plan, authority)["status"], "needs-decision")
            self.assertEqual(host.requests, [])
        self.assertEqual(self.apply(host, plan)["status"], "verified")

    def test_unknown_decision_is_persisted_and_not_repeated(self):
        plan = self.build(FakeMigrationRunner({**CONFIG, "prompt": "Custom human text"}))
        path = self.root / "decisions.json"
        first = remember_decision(path, plan)
        raw = path.read_bytes()
        self.assertTrue(first["ask_again"])
        second = remember_decision(path, plan)
        self.assertFalse(second["ask_again"])
        self.assertEqual(path.read_bytes(), raw)
        remember_decision(path, plan, decision="declined", source="human fixture decision")
        self.assertEqual(remember_decision(path, plan)["decision"], "declined")
        host=FakeMigrationRunner({**CONFIG,"prompt":"Custom human text","updated_at":99})
        host.revision=10
        fresh=self.build(host)
        self.assertNotEqual(fresh["plan_id"],plan["plan_id"])
        self.assertFalse(remember_decision(path,fresh)["ask_again"])
        self.assertEqual(remember_decision(path,fresh)["decision"],"declined")

    def test_terminal_pause_eligibility_independent_of_migration(self):
        runner = {"expected": {"id": "fixture"}, "observed": {"id": "fixture", "status": "ACTIVE"},
                  "capabilities": {"readback": True, "status_update": True}}
        decision = {"decision": "pending", "plan_id": "unresolved"}
        result = decide_control({"status": "completed", "all_phases_complete": True}, POLICY,
                                {"migration_decision": decision}, runner)
        self.assertEqual(result["action"], "reconcile_completion")
        self.assertIn("pause_status_only", [x["operation"] for x in result["required_effects"]])

    def test_acknowledgement_loss_resumes_without_repeating_host_update(self):
        host = FakeMigrationRunner(); plan = self.build(host);host.ack_lost = True
        first = self.apply(host, plan)
        self.assertNotEqual(first["status"], "verified")
        self.assertIsNone(first["receipt"])
        second = self.apply(host, plan)
        self.assertEqual(second["status"], "verified")
        self.assertEqual(len(host.requests), 1)

    def test_no_readback_no_update_claim_and_bounded_retries(self):
        host = FakeMigrationRunner(); plan = self.build(host); host.ignore = True
        for _ in range(3):
            result = self.apply(host, plan)
            self.assertEqual(result["status"], "applied")
            self.assertIsNone(result["receipt"])
        result = self.apply(host, plan)
        self.assertEqual(result["status"], "needs-decision")
        self.assertEqual(len(host.requests), 3)
        with self.assertRaises(RunnerError):
            record_verified_migration({}, plan, result)

    def test_concurrent_runner_identity_settings_and_policy_edits_fail_closed(self):
        for field, value in (("id", "other"), ("cwds", ["/other"]), ("model", "other"),
                             ("prompt", CONFIG["prompt"]+"Human edit")):
            host=FakeMigrationRunner();plan=self.build(host);host.config[field]=value
            result=self.apply(host, plan)
            self.assertNotEqual(result["status"], "verified")
            self.assertEqual(host.requests, [])
        host=FakeMigrationRunner();plan=self.build(host);host.concurrent=True
        result=self.apply(host,plan)
        self.assertNotEqual(result["status"], "verified")
        self.assertIn("Human edit",host.config["prompt"])
        host=FakeMigrationRunner();plan=self.build(host)
        write_json_object(self.policy,{**POLICY,"pause_automation_on_completion":False})
        self.assertEqual(self.apply(host,plan)["status"],"needs-decision")
        self.assertEqual(host.requests,[])

    def test_host_changes_unrelated_settings_is_not_a_verified_migration(self):
        host=FakeMigrationRunner();plan=self.build(host);host.corrupt_settings=True
        result=self.apply(host,plan)
        self.assertEqual(result["status"],"applied")
        self.assertIsNone(result["receipt"])
        self.assertEqual(self.apply(host,plan)["status"],"needs-decision")

    def test_exact_plan_integrity_prevents_authority_or_payload_expansion(self):
        host=FakeMigrationRunner();plan=self.build(host)
        for key,value in (("plan_id","tampered"),("after",{**plan["after"],"model":"other"}),
                          ("effects",["update_prompt_only","promote_main"])):
            altered={**plan,key:value}
            with self.assertRaises(RunnerError):validate_plan(altered)
        self.assertEqual(host.requests,[])

    def test_bounded_rollback_preserves_subsequent_settings_but_never_prompt_edits(self):
        host=FakeMigrationRunner();plan=self.build(host)
        self.assertEqual(self.apply(host,plan)["status"],"verified")
        host.config["model"]="operator-later-model"
        rollback=rollback_plan(plan,host.readback("fixture"),POLICY)
        self.assertEqual(rollback["status"],"planned")
        self.assertEqual(rollback["payload"]["model"],"operator-later-model")
        result=self.apply(host,plan,direction="rollback")
        self.assertEqual(result["status"],"verified")
        self.assertEqual(host.config["prompt"],CONFIG["prompt"])
        self.assertEqual(host.config["model"],"operator-later-model")
        # Human prompt edits are always protected, even with the old approval.
        host.config["prompt"]="later human text"
        self.assertEqual(rollback_plan(plan,host.readback("fixture"),POLICY)["status"],"needs-decision")
        self.assertEqual(self.apply(host,plan,direction="rollback")["status"],"needs-decision")

    def test_rollback_policy_conflict_preserves_operator_edits(self):
        legacy={k:v for k,v in POLICY.items() if not k.startswith("pause_automation_on_")}
        write_json_object(self.policy,legacy)
        host=FakeMigrationRunner();plan=self.build(host,legacy,policy_path=str(self.policy))
        self.assertEqual(self.apply(host,plan)["status"],"verified")
        changed={**POLICY,"pause_automation_on_stall":False}
        write_json_object(self.policy,changed)
        self.assertEqual(self.apply(host,plan,direction="rollback")["status"],"needs-decision")
        self.assertEqual(load_json_object(self.policy),changed)

    def test_unavailable_adapter_and_untrusted_readback_are_truthful(self):
        host=FakeMigrationRunner();plan=self.build(host);host.update_prompt_only=None
        self.assertEqual(self.apply(host,plan)["status"],"needs-decision")
        with self.assertRaises(RunnerError):
            plan_migration({**host.readback("fixture"),"scheduler_authoritative":False},EXPECTED,SLUG,POLICY)

    def test_mid_update_policy_edit_never_receives_stale_verified_receipt(self):
        host=FakeMigrationRunner();plan=self.build(host)
        original=host.update_prompt_only
        changed={**POLICY,"pause_automation_on_completion":False}
        def edit_during_update(request):
            original(request)
            write_json_object(self.policy,changed)
        host.update_prompt_only=edit_during_update
        result=self.apply(host,plan)
        self.assertEqual(result["status"],"needs-decision")
        self.assertIsNone(result["receipt"])
        self.assertEqual(load_json_object(self.policy),changed)
        self.assertEqual(host.config["prompt"],plan["after"]["prompt"])

    def test_exact_pending_authority_decision_is_not_reasked_or_rewritten(self):
        host=FakeMigrationRunner();plan=self.build(host)
        first=self.apply(host,plan,authority=None)
        self.assertTrue(first["ask_again"])
        raw=self.journal.read_bytes()
        second=self.apply(host,plan,authority=None)
        self.assertFalse(second["ask_again"])
        self.assertEqual(raw,self.journal.read_bytes())

    def test_policy_write_scope_is_bound_to_exact_authorized_path(self):
        legacy={k:v for k,v in POLICY.items() if not k.startswith("pause_automation_on_")}
        write_json_object(self.policy,legacy)
        host=FakeMigrationRunner();plan=self.build(host,legacy,policy_path=str(self.policy))
        other=self.root/"other-policy.json";write_json_object(other,legacy)
        result=resume_migration(plan,self.journal,adapter=host,authority=auth(plan),policy_path=other)
        self.assertEqual(result["status"],"needs-decision")
        self.assertEqual(load_json_object(other),legacy)
        self.assertEqual(host.requests,[])
        unbound=build(host,legacy)
        self.assertEqual(self.apply(host,unbound)["status"],"needs-decision")

    def test_prompt_only_also_binds_policy_path_and_cannot_use_substitute(self):
        host = FakeMigrationRunner(); plan = self.build(host)
        other = self.root / "substitute.json"; write_json_object(other, POLICY)
        changed = {**POLICY, "pause_automation_on_completion": False}
        write_json_object(self.policy, changed)
        result = resume_migration(plan, self.journal, adapter=host, authority=auth(plan), policy_path=other)
        self.assertEqual(result["status"], "needs-decision")
        self.assertEqual(host.requests, [])
        self.assertEqual(self.apply(host, build(host))["status"], "needs-decision")

    def test_noop_still_requires_fresh_runner_and_policy_readback(self):
        host = FakeMigrationRunner({**CONFIG, "prompt": render_prompt(SLUG)})
        plan = self.build(host)
        self.assertEqual(plan["effects"], [])
        result = self.apply(host, plan, authority=None)
        self.assertEqual(result["status"], "verified")
        self.assertTrue(result["receipt"]["scheduler_authoritative"])
        host.config["prompt"] = "Human edited prompt"
        self.assertEqual(self.apply(host, plan, authority=None)["status"], "needs-decision")
        with patch.object(host, "readback", side_effect=OSError("unavailable")):
            self.assertNotEqual(self.apply(host, plan, authority=None)["status"], "verified")

    def test_policy_only_rollback_requires_new_plan_and_failures_are_bounded(self):
        legacy = {k: v for k, v in POLICY.items() if not k.startswith("pause_automation_on_")}
        write_json_object(self.policy, legacy)
        host = FakeMigrationRunner({**CONFIG, "prompt": render_prompt(SLUG)})
        plan = self.build(host, legacy)
        self.assertEqual(plan["effects"], ["write_policy"])
        self.assertEqual(self.apply(host, plan)["status"], "verified")
        rollback = self.apply(host, plan, direction="rollback")
        self.assertEqual(rollback["status"], "verified")
        self.assertEqual(self.apply(host, plan)["status"], "needs-decision")
        self.assertEqual(load_json_object(self.policy), legacy)
        fresh = plan_migration(host.readback("fixture"), EXPECTED, SLUG, legacy,
            roadmap=ROADMAP, policy_path=str(self.policy), supersedes_rollback=digest(rollback["receipt"]))
        self.assertNotEqual(fresh["plan_id"], plan["plan_id"])
        self.assertEqual(self.apply(host, fresh, authority=auth(plan))["status"], "needs-decision")
        self.assertEqual(self.apply(host, fresh)["status"], "verified")
        write_json_object(self.policy, legacy)
        self.journal.unlink()
        with patch("roadmap_delivery.migrations.write_json_object", side_effect=lambda path, value: (_ for _ in ()).throw(OSError("write failed")) if path == self.policy else write_json_object(path, value)):
            for n in range(5):
                result = self.apply(host, plan)
                self.assertEqual(result["attempts"], min(n + 1, 3))
                self.assertEqual(result["status"], "planned" if n < 3 else "needs-decision")
        self.assertEqual(host.requests, [])

    def test_prompt_version_matches_canonical_template_and_installed_cli_is_portable(self):
        repo=Path(__file__).resolve().parents[1]
        template=(repo/"core/templates/automation_prompt.md").read_text().split("```text\n",1)[1].split("\n```",1)[0]
        self.assertEqual(render_prompt("fixture",template),render_prompt("fixture"))
        package=self.root/"installed"
        shutil.copytree(repo/"skill/roadmap-delivery-skill",package,ignore=shutil.ignore_patterns("__pycache__"))
        snapshot=self.root/"runner.json";write_json_object(snapshot,FakeMigrationRunner().readback("fixture"))
        expected=self.root/"expected.json";write_json_object(expected,EXPECTED)
        proc=subprocess.run([sys.executable,"-I","-S",str(package/"scripts/roadmap_delivery.py"),"plan-migration",
                             "--roadmap-slug","fixture","--roadmap-path",ROADMAP,"--runner-snapshot",str(snapshot),
                             "--expected-file",str(expected),"--policy-file",str(self.policy),"--json"],
                            cwd=self.root,text=True,capture_output=True)
        self.assertEqual(proc.returncode,0,proc.stderr or proc.stdout)
        result=json.loads(proc.stdout)
        self.assertEqual(result["status"],"planned")
        self.assertEqual(result["provenance"]["prompt_source"],"9c0d7ae^")

    def test_failed_rollback_recheck_preserves_receipt_and_cannot_revive_forward_authority(self):
        legacy = {k: v for k, v in POLICY.items() if not k.startswith("pause_automation_on_")}
        for failure in ("authority", "readback"):
            with self.subTest(failure=failure):
                self.journal.unlink(missing_ok=True)
                write_json_object(self.policy, legacy)
                host = FakeMigrationRunner({**CONFIG, "prompt": render_prompt(SLUG)})
                plan = self.build(host, legacy)
                forward = self.apply(host, plan)
                rollback = self.apply(host, plan, direction="rollback")
                if failure == "authority":
                    failed = self.apply(host, plan, direction="rollback", authority=None)
                else:
                    with patch.object(host, "readback", side_effect=OSError("unavailable")):
                        failed = self.apply(host, plan, direction="rollback")
                self.assertNotEqual(failed["status"], "verified")
                self.assertEqual(failed["receipt"], rollback["receipt"])
                rejected = self.apply(host, plan)
                self.assertEqual(rejected["status"], "needs-decision")
                self.assertEqual(rejected["receipt"], forward["receipt"])
                self.assertEqual(load_json_object(self.policy), legacy)
                fresh = plan_migration(host.readback(SLUG), EXPECTED, SLUG, legacy,
                    roadmap=ROADMAP, policy_path=str(self.policy), supersedes_rollback=digest(rollback["receipt"]))
                self.assertEqual(self.apply(host, fresh)["status"], "verified")
                entries = load_json_object(self.journal)["entries"]
                self.assertEqual(entries[plan["plan_id"] + ":rollback"]["receipt"], rollback["receipt"])

    def test_superseded_authority_is_retired_before_effects_and_survives_interruption(self):
        legacy = {k: v for k, v in POLICY.items() if not k.startswith("pause_automation_on_")}
        for explicit_link in (True, False):
            with self.subTest(explicit_link=explicit_link):
                self.journal.unlink(missing_ok=True)
                write_json_object(self.policy, legacy)
                host = FakeMigrationRunner({**CONFIG, "prompt": render_prompt(SLUG)})
                plan = self.build(host, legacy)
                forward = self.apply(host, plan)
                rollback = self.apply(host, plan, direction="rollback")
                host.revision += 1
                fresh = plan_migration(host.readback(SLUG), EXPECTED, SLUG, legacy,
                    roadmap=ROADMAP, policy_path=str(self.policy),
                    supersedes_rollback=digest(rollback["receipt"]) if explicit_link else None)
                def fail_policy(path, value):
                    if path == self.policy:
                        raise OSError("interrupted policy write")
                    write_json_object(path, value)
                with patch("roadmap_delivery.migrations.write_json_object", side_effect=fail_policy):
                    self.assertEqual(self.apply(host, fresh)["status"], "planned")
                for direction, original in (("forward", forward), ("rollback", rollback)):
                    rejected = self.apply(host, plan, direction=direction)
                    self.assertEqual(rejected["status"], "needs-decision")
                    self.assertIn("superseded", rejected["required_action"])
                    self.assertEqual(rejected["receipt"], original["receipt"])
                    self.assertEqual(rejected["attempts"], original["attempts"])
                self.assertEqual(self.apply(host, fresh)["status"], "verified")
                self.assertEqual(self.apply(host, plan, direction="rollback")["status"], "needs-decision")
                self.assertEqual(load_json_object(self.policy), POLICY)
                self.assertEqual(self.apply(host, fresh, direction="rollback")["status"], "verified")
                self.assertEqual(self.apply(host, plan, direction="rollback")["status"], "needs-decision")
                self.assertEqual(load_json_object(self.policy), legacy)

    def test_verified_receipt_is_immutable_across_rechecks_and_changed_owned_values(self):
        legacy = {k: v for k, v in POLICY.items() if not k.startswith("pause_automation_on_")}
        write_json_object(self.policy, legacy)
        host = FakeMigrationRunner({**CONFIG, "prompt": render_prompt(SLUG)})
        plan = self.build(host, legacy)
        original = self.apply(host, plan)
        with patch.object(host, "readback", side_effect=OSError("unavailable")):
            self.assertEqual(self.apply(host, plan)["receipt"], original["receipt"])
        host.revision += 1
        checked = self.apply(host, plan)
        self.assertEqual(checked["status"], "verified")
        self.assertEqual(checked["receipt"], original["receipt"])
        write_json_object(self.policy, legacy)
        rejected = self.apply(host, plan)
        self.assertEqual(rejected["status"], "needs-decision")
        self.assertEqual(rejected["attempts"], original["attempts"])
        self.assertEqual(rejected["receipt"], original["receipt"])
        self.assertEqual(load_json_object(self.policy), legacy)

    def test_superseding_plan_cannot_bind_another_runners_rollback(self):
        host = FakeMigrationRunner(); plan = self.build(host)
        self.apply(host, plan)
        rollback = self.apply(host, plan, direction="rollback")
        other = FakeMigrationRunner({**CONFIG, "id": "another-runner"})
        fresh = plan_migration(other.readback("another-runner"), {**EXPECTED, "id": "another-runner"},
            SLUG, POLICY, roadmap=ROADMAP, policy_path=str(self.policy),
            supersedes_rollback=digest(rollback["receipt"]))
        result = self.apply(other, fresh, authority={**auth(fresh), "runner_id": "another-runner"})
        self.assertEqual(result["status"], "needs-decision")
        self.assertEqual(other.requests, [])

    def test_rolled_back_plan_needs_fresh_authorization_before_upgrade_again(self):
        host=FakeMigrationRunner();plan=self.build(host)
        self.assertEqual(self.apply(host,plan)["status"],"verified")
        self.assertEqual(self.apply(host,plan,direction="rollback")["status"],"verified")
        count=len(host.requests)
        self.assertEqual(self.apply(host,plan)["status"],"needs-decision")
        self.assertEqual(len(host.requests),count)
        fresh=self.build(host)
        self.assertNotEqual(fresh["plan_id"],plan["plan_id"])
        self.assertEqual(self.apply(host,fresh,authority=auth(plan))["status"],"needs-decision")
        self.assertEqual(self.apply(host,fresh)["status"],"verified")

    def test_runner_edit_during_local_policy_write_cannot_be_verified(self):
        legacy={k:v for k,v in POLICY.items() if not k.startswith("pause_automation_on_")}
        write_json_object(self.policy,legacy)
        host=FakeMigrationRunner();plan=self.build(host,legacy,policy_path=str(self.policy))
        def write_and_edit(path,value):
            write_json_object(path,value)
            if path==self.policy:
                host.config["model"]="human concurrent model"
                host.revision+=1
        with patch("roadmap_delivery.migrations.write_json_object",side_effect=write_and_edit):
            result=self.apply(host,plan)
        self.assertEqual(result["status"],"needs-decision")
        self.assertIsNone(result["receipt"])
        self.assertEqual(host.config["model"],"human concurrent model")


if __name__ == "__main__":
    unittest.main()
