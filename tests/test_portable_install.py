"""Behavioral installs: no checkout imports, PYTHONPATH, or runtime site packages."""
import json
import os
import shlex
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from tests import test_install_smoke as smoke
from tests.test_install_smoke import REPO_ROOT, DEMO_SLUG, DEMO_AUTOMATION_ID


class PortableInstallTests(unittest.TestCase):
    def test_ci_and_published_action_examples_use_supported_python(self):
        import re
        for name in (".github/workflows/host-smoke-nightly.yml", "docs/github-action.md",
                     ".github/actions/roadmap-delivery-validate/README.md"):
            pins = re.findall(r"python-version:\s*['\"]([^'\"]+)", (REPO_ROOT / name).read_text())
            self.assertTrue(pins, name)
            self.assertEqual(set(pins), {"3.12"}, name)
        self.assertNotIn("write_control_bridges", (REPO_ROOT / "docs/runtime-control-contract.md").read_text())

    @classmethod
    def setUpClass(cls):
        cls.storage = tempfile.TemporaryDirectory(prefix="portable-release-")
        proc = subprocess.run([sys.executable, "scripts/build_release.py", "--output-dir", cls.storage.name, "--json"],
                              cwd=REPO_ROOT, capture_output=True, text=True)
        if proc.returncode:
            raise AssertionError(proc.stderr or proc.stdout)
        cls.artifacts = {item["kind"]: Path(item["path"]) for item in json.loads(proc.stdout)["artifacts"]}

    @classmethod
    def tearDownClass(cls):
        cls.storage.cleanup()

    def fixture(self, root):
        helper = smoke.InstallSmokeTests()
        project = helper.copy_demo_repo(root)
        env = helper.env_with_config(root, project, REPO_ROOT / "examples/demo-roadmap/automation-config" / DEMO_AUTOMATION_ID / "automation.toml")
        env.pop("PYTHONPATH", None)
        env.pop("PYTHONHOME", None)
        env["PYTHONNOUSERSITE"] = "1"
        env["PIP_NO_INDEX"] = "1"
        env["PIP_CONFIG_FILE"] = os.devnull
        return project, env

    def stage(self, root, host, release):
        if release:
            target = root / "extract"
            shutil.unpack_archive(str(self.artifacts[host + ("_skill_package" if host == "codex" else "_plugin_package")]), target)
            package = next(target.iterdir())
        else:
            package = root / "install"
            shutil.copytree(REPO_ROOT / ("skill/roadmap-delivery-skill" if host == "codex" else "dist/claude"), package)
        return package if host == "codex" else package / "skills/roadmap-delivery-skill"

    def execute(self, skill, project, env, helper, *args, codes=(0,)):
        proc = subprocess.run([sys.executable, "-I", "-S", str(skill / "scripts" / helper), *args],
                              cwd=project, env=env, capture_output=True, text=True)
        self.assertIn(proc.returncode, codes, proc.stderr or proc.stdout)
        return json.loads(proc.stdout)

    def exercise(self, skill, project, env):
        common = ["--repo-root", str(project), "--roadmap-slug", DEMO_SLUG, "--automation-id", DEMO_AUTOMATION_ID, "--json"]
        validation = self.execute(skill, project, env, "validate_delivery_artifacts.py", *common, "--strict")
        self.assertEqual(validation["errors"], [])
        self.assertEqual(validation["warnings"], [])
        # A schema-only invalidity must be caught by the bundled schema.
        state_path = project / "automation/demo_roadmap/delivery_state.json"
        if not state_path.exists():
            state_path = project / "automation/demo-roadmap/delivery_state.json"
        original = state_path.read_text()
        state = json.loads(original)
        state["run_count"] = -5
        state_path.write_text(json.dumps(state))
        bad = self.execute(skill, project, env, "validate_delivery_artifacts.py", *common, codes=(1,))
        self.assertTrue(any("schema" in item["code"] for item in bad["errors"]), bad)
        state_path.write_text(original)
        self.execute(skill, project, env, "inspect_delivery_state.py", *common)
        self.execute(skill, project, env, "compute_progress_signature.py", *common)
        self.execute(skill, project, env, "plan_automation_retarget.py", *common, "--delivered-phase", "Phase 0 - Establish Fixture Contract")
        # Prerequisite scanner may surface fixture approvals; the command still runs.
        self.execute(skill, project, env, "plan_phase_prerequisites.py", *common, codes=(0, 1))
        self.execute(skill, project, env, "roadmap_delivery.py", "plan-control", *common, codes=(0, 1))
        self.execute(skill, project, env, "roadmap_delivery.py", "scaffold", "--repo-root", str(project),
                     "--roadmap-slug", "portable-new", "--dry-run", "--json")
        self.execute(skill, project, env, "compute_progress_signature.py", *common, "--start-run", "--run-id", "portable-one")
        outcome = self.execute(skill, project, env, "compute_progress_signature.py", *common, "--record-run", "--run-id", "portable-one")
        self.assertTrue(outcome["recorded"])
        self.execute(skill, project, env, "write_operator_alert.py", "--repo-root", str(project), "--roadmap-slug", DEMO_SLUG,
                     "--kind", "blocked", "--reason", "Portable diagnostic", "--json")
        code = "import runpy,sys,json; runpy.run_path(sys.argv[1]); import roadmap_delivery,roadmap_delivery.paths; print(json.dumps({'module':roadmap_delivery.__file__,'resources':str(roadmap_delivery.paths.runtime_resource_root()),'paths':sys.path,'modules':{k:v.__file__ for k,v in sys.modules.items() if k.startswith('roadmap_delivery') and hasattr(v,'__file__')}}))"
        proc = subprocess.run([sys.executable, "-I", "-S", "-c", code, str(skill / "scripts/inspect_delivery_state.py")],
                              cwd=project, env=env, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        origins = json.loads(proc.stdout)
        self.assertTrue(Path(origins["module"]).is_relative_to((skill / "runtime").resolve()), origins)
        self.assertTrue(Path(origins["resources"]).is_relative_to((skill / "runtime").resolve()), origins)
        self.assertTrue(all(Path(origin).is_relative_to((skill / "runtime").resolve()) for origin in origins["modules"].values()), origins)
        self.assertFalse(any(str(REPO_ROOT) in item or "site-packages" in item for item in origins["paths"]), origins)

    def test_skill_directories_and_extracted_releases_execute_all_helpers(self):
        for host in ("codex", "claude"):
            for release in (False, True):
                with self.subTest(host=host, release=release), tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    skill = self.stage(root, host, release)
                    project, env = self.fixture(root)
                    self.exercise(skill, project, env)

    def test_missing_schema_and_mixed_resources_fail_without_project_fallback(self):
        for corruption in ("schema", "version", "module", "manifest", "invalid_manifest"):
            with self.subTest(corruption=corruption), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                skill = self.stage(root, "codex", True)
                project, env = self.fixture(root)
                shutil.copytree(REPO_ROOT / "schemas", project / "schemas")
                package = skill / "runtime/roadmap_delivery"
                resources = package / "_resources"
                if corruption == "schema":
                    (resources / "schemas/delivery_state.schema.json").unlink()
                elif corruption == "version":
                    manifest_path = resources / "runtime-manifest.json"
                    manifest = json.loads(manifest_path.read_text()); manifest["version"] = "99.0.0"
                    manifest_path.write_text(json.dumps(manifest))
                elif corruption == "module":
                    with (package / "approval.py").open("a") as f:
                        f.write("\n# changed module\n")
                elif corruption == "invalid_manifest":
                    (resources / "runtime-manifest.json").write_text("[]")
                else:
                    (resources / "runtime-manifest.json").unlink()
                proc = subprocess.run([sys.executable, "-I", "-S", str(skill / "scripts/validate_delivery_artifacts.py"),
                                       "--repo-root", str(project), "--roadmap-slug", DEMO_SLUG, "--json"],
                                      cwd=project, env=env, capture_output=True, text=True)
                self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
                self.assertIn("reinstall", proc.stderr.lower())

    def test_cli_source_installs_offline_into_fresh_venv(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.unpack_archive(str(self.artifacts["cli_source_package"]), root / "source")
            source = next((root / "source").iterdir())
            project, env = self.fixture(root)
            (project / "VERSION").write_text("7.8.9\n")
            venv = project / ".venv"
            subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(venv)], env=env, check=True, capture_output=True)
            wheels = root / "wheels"
            build = subprocess.run([sys.executable, "-m", "pip", "wheel", "--no-index", "--no-deps", "--no-build-isolation",
                                    "--wheel-dir", str(wheels), str(source)], cwd=project, env=env, capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stderr or build.stdout)
            install = subprocess.run([sys.executable, "-m", "pip", "--python", str(venv / "bin/python"), "install",
                                      "--no-index", "--no-deps", str(next(wheels.glob('*.whl')))], cwd=project, env=env, capture_output=True, text=True)
            self.assertEqual(install.returncode, 0, install.stderr or install.stdout)
            command = [str(venv / "bin/roadmap-delivery"), "validate", "--repo-root", str(project), "--roadmap-slug", DEMO_SLUG,
                       "--automation-id", DEMO_AUTOMATION_ID, "--strict", "--allow-warning", "worktree_dirty", "--json"]
            check = subprocess.run(command, cwd=project, env=env, capture_output=True, text=True)
            self.assertEqual(check.returncode, 0, check.stderr or check.stdout)
            self.assertEqual(json.loads(check.stdout)["errors"], [])
            probe = subprocess.run([str(venv / "bin/python"), "-I", "-c", "import roadmap_delivery,roadmap_delivery.paths; print(roadmap_delivery.__file__); print(roadmap_delivery.paths.runtime_resource_root())"],
                                   cwd=project, env=env, capture_output=True, text=True)
            self.assertEqual(probe.returncode, 0, probe.stderr)
            self.assertTrue(all(str(venv) in line for line in probe.stdout.splitlines()), probe.stdout)
            self.assertNotIn(str(REPO_ROOT), probe.stdout)
            self.assertFalse((venv / "lib/python3.12/site-packages/tomli").exists())

    def test_older_python_has_explicit_migration_error(self):
        older = Path('/usr/bin/python3')
        if not older.exists() or sys.version_info[:2] < (3, 12):
            self.skipTest('separate older interpreter unavailable')
        version = subprocess.check_output([str(older), '-c', 'import sys; print(sys.version_info[:2])'], text=True).strip()
        if version == '(3, 12)':
            self.skipTest('older interpreter unavailable')
        with tempfile.TemporaryDirectory() as tmp:
            skill = self.stage(Path(tmp), 'codex', True)
            proc = subprocess.run([str(older), '-S', str(skill / 'scripts/inspect_delivery_state.py'), '--help'],
                                  cwd=tmp, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 2)
            self.assertIn('Python 3.12', proc.stderr)

    def test_missing_runtime_never_borrows_an_available_checkout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            checkout = root / "checkout"
            checkout.mkdir()
            shutil.copytree(REPO_ROOT / "src", checkout / "src", ignore=shutil.ignore_patterns("__pycache__"))
            (checkout / "pyproject.toml").write_text("# available development checkout")
            (checkout / "adapters").mkdir()
            skill = checkout / "skill/roadmap-delivery-skill"
            shutil.copytree(REPO_ROOT / "skill/roadmap-delivery-skill", skill)
            shutil.rmtree(skill / "runtime")
            proc = subprocess.run([sys.executable, "-I", "-S", str(skill / "scripts/inspect_delivery_state.py"), "--help"],
                                  cwd=root, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 2)
            self.assertIn("reinstall", proc.stderr)

    def test_scaffold_emitted_commands_execute_without_cli_installation(self):
        for host in ("codex", "claude"):
            with self.subTest(host=host), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); skill = self.stage(root, host, True)
                project, env = self.fixture(root)
                result = self.execute(skill, project, env, "roadmap_delivery.py", "scaffold",
                    "--repo-root", str(project), "--roadmap-slug", "new-scope", "--json")
                for command in result["next_commands"]:
                    proc = subprocess.run(shlex.split(command), cwd=project, env=env, capture_output=True, text=True)
                    self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)
                    self.assertNotIn("ModuleNotFoundError", proc.stderr)
                guide = project / "automation/new_scope/automation_guide.md"
                self.assertTrue(guide.is_file())
                self.assertTrue(all(command in guide.read_text() for command in result["next_commands"]))

    def test_claude_damaged_hook_cannot_borrow_ancestor_checkout(self):
        with tempfile.TemporaryDirectory() as tmp:
            checkout = Path(tmp) / "checkout"; checkout.mkdir()
            shutil.copytree(REPO_ROOT / "src", checkout / "src", ignore=shutil.ignore_patterns("__pycache__"))
            (checkout / "pyproject.toml").write_text("# development checkout")
            (checkout / "adapters").mkdir()
            plugin = checkout / "nested/plugin"
            shutil.copytree(REPO_ROOT / "dist/claude", plugin)
            shutil.rmtree(plugin / "skills/roadmap-delivery-skill/runtime")
            proc = subprocess.run([sys.executable, "-I", "-S", str(plugin / "hooks/roadmap_delivery_safety.py"), "guard-bash"],
                input=json.dumps({"tool_name": "Bash", "tool_input": {"command": "git reset --hard"}}),
                cwd=tmp, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
            self.assertIn("reinstall", proc.stderr)

    def test_claude_host_default_is_local_and_explicit_override_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = self.stage(root, "claude", True)
            project, env = self.fixture(root)
            env.pop("AUTONOMOUS_ROADMAP_AUTOMATIONS_DIR")
            code = "import runpy,sys; runpy.run_path(sys.argv[1]); from roadmap_delivery.reports import AUTOMATIONS_DIR; print(AUTOMATIONS_DIR)"
            for override in (None, root / "explicit-automations"):
                if override is not None:
                    env["AUTONOMOUS_ROADMAP_AUTOMATIONS_DIR"] = str(override)
                proc = subprocess.run([sys.executable, "-I", "-S", "-c", code, str(skill / "scripts/inspect_delivery_state.py")],
                                      cwd=project, env=env, capture_output=True, text=True)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                expected = override or Path(env["HOME"]) / ".claude/roadmap-delivery/automations"
                self.assertEqual(Path(proc.stdout.strip()), expected)

    def test_helper_execution_bytecode_does_not_create_build_drift(self):
        env = os.environ.copy()
        env.pop("PYTHONPYCACHEPREFIX", None)
        proc = subprocess.run([sys.executable, "-I", "-S", str(REPO_ROOT / "skill/roadmap-delivery-skill/scripts/inspect_delivery_state.py"), "--help"],
                              cwd=self.storage.name, env=env, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        for builder in ("build_adapters.py", "build_codex_package.py"):
            proc = subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / builder), "--repo-root", str(REPO_ROOT), "--check", "--json"],
                                  cwd=self.storage.name, env=env, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)
