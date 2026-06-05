import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VERSION = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()


class ReleaseBuilderTests(unittest.TestCase):
    maxDiff = None

    def build_release(self, output_dir):
        proc = subprocess.run(
            [
                sys.executable,
                "scripts/build_release.py",
                "--output-dir",
                str(output_dir),
                "--json",
            ],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)
        return json.loads(proc.stdout)

    def test_build_release_checksum_file_round_trips(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "dist"
            report = self.build_release(output_dir)
            self.assertEqual(report["adapter_check"]["status"], "passed")
            self.assertEqual(report["codex_artifact_validation"]["status"], "passed")
            self.assertEqual(report["claude_artifact_validation"]["status"], "passed")
            self.assertEqual(report["generic_artifact_validation"]["status"], "passed")

            artifact_kinds = {item["kind"] for item in report["artifacts"]}
            self.assertEqual(
                artifact_kinds,
                {
                    "source_archive",
                    "codex_skill_package",
                    "claude_plugin_package",
                    "schema_bundle",
                    "cli_source_package",
                    "generic_markdown_pack",
                    "release_manifest",
                    "checksums",
                },
            )
            checksum_artifact = next(item for item in report["artifacts"] if item["kind"] == "checksums")
            checksum_path = Path(checksum_artifact["path"])

            self.assertTrue(checksum_path.is_file())
            expected = {
                item["filename"]: item["sha256"]
                for item in report["artifacts"]
                if item["kind"] != "checksums"
            }
            observed = {}
            for line in checksum_path.read_text(encoding="utf-8").splitlines():
                digest, filename = line.split("  ", 1)
                artifact_path = output_dir / filename
                self.assertTrue(artifact_path.is_file(), filename)
                observed[filename] = digest
                actual = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
                self.assertEqual(actual, digest)

            self.assertEqual(observed, expected)

    def test_build_release_contains_multi_host_packages(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "dist"
            report = self.build_release(output_dir)
            artifacts = {item["kind"]: Path(item["path"]) for item in report["artifacts"]}

            with tarfile.open(artifacts["claude_plugin_package"], "r:gz") as archive:
                names = set(archive.getnames())
            self.assertIn(
                f"roadmap-delivery-claude-plugin-{VERSION}/.claude-plugin/plugin.json",
                names,
            )
            self.assertIn(
                f"roadmap-delivery-claude-plugin-{VERSION}/skills/roadmap-delivery-skill/SKILL.md",
                names,
            )
            self.assertIn(f"roadmap-delivery-claude-plugin-{VERSION}/agents/reviewer.md", names)
            self.assertIn(f"roadmap-delivery-claude-plugin-{VERSION}/hooks/hooks.json", names)

            with tarfile.open(artifacts["generic_markdown_pack"], "r:gz") as archive:
                names = set(archive.getnames())
            self.assertIn(f"roadmap-delivery-generic-markdown-pack-{VERSION}/README.md", names)
            self.assertIn(
                f"roadmap-delivery-generic-markdown-pack-{VERSION}/workflow/phase-loop.md",
                names,
            )
            self.assertIn(
                f"roadmap-delivery-generic-markdown-pack-{VERSION}/schemas/delivery_state.schema.json",
                names,
            )

            manifest = json.loads((output_dir / f"roadmap-delivery-{VERSION}-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["compatibility"]["supported_host_packages"], ["codex", "claude"])
            self.assertEqual(manifest["compatibility"]["claude_plugin_path"], "dist/claude")

    def test_source_archives_ignore_generated_package_metadata(self):
        egg_info = REPO_ROOT / "src" / "roadmap_delivery_release_test.egg-info"
        self.assertFalse(egg_info.exists(), f"Test fixture path already exists: {egg_info}")
        try:
            egg_info.mkdir()
            (egg_info / "PKG-INFO").write_text("Name: roadmap-delivery-release-test\n", encoding="utf-8")
            (egg_info / "SOURCES.txt").write_text("generated metadata\n", encoding="utf-8")
            with tempfile.TemporaryDirectory() as tmp:
                output_dir = Path(tmp) / "dist"
                report = self.build_release(output_dir)
                artifacts = {item["kind"]: Path(item["path"]) for item in report["artifacts"]}

                for kind in ("source_archive", "cli_source_package"):
                    with self.subTest(kind=kind):
                        with tarfile.open(artifacts[kind], "r:gz") as archive:
                            names = archive.getnames()
                        self.assertFalse(
                            any(".egg-info/" in name or name.endswith(".egg-info") for name in names),
                            f"{kind} should exclude generated egg-info metadata",
                        )
        finally:
            shutil.rmtree(egg_info, ignore_errors=True)

    def test_manifest_records_release_notes_packages_and_capabilities(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "dist"
            report = self.build_release(output_dir)
            manifest = json.loads((output_dir / f"roadmap-delivery-{VERSION}-manifest.json").read_text(encoding="utf-8"))

            artifact_by_filename = {
                item["filename"]: item
                for item in report["artifacts"]
                if item["kind"] not in {"release_manifest", "checksums"}
            }
            self.assertEqual(manifest["release_notes"]["path"], f"docs/release-notes-{VERSION}.md")
            self.assertIn("known limitations", manifest["release_notes"]["source_of_truth_for"])
            self.assertIn("python3 scripts/build_release.py --check --json", manifest["verification_commands"])

            packages = {item["name"]: item for item in manifest["packages"]}
            self.assertEqual(
                sorted(packages),
                [
                    "roadmap-delivery-claude-plugin",
                    "roadmap-delivery-codex-skill",
                    "roadmap-delivery-generic-markdown-pack",
                ],
            )
            for package in packages.values():
                with self.subTest(package=package["name"]):
                    self.assertEqual(package["version"], VERSION)
                    self.assertIn(package["artifact"], artifact_by_filename)
                    self.assertEqual(package["sha256"], artifact_by_filename[package["artifact"]]["sha256"])
                    self.assertGreater(len(package["capability_summary"]), 1)
                    self.assertGreater(len(package["limitations"]), 0)

            self.assertEqual(packages["roadmap-delivery-codex-skill"]["host"], "codex")
            self.assertEqual(packages["roadmap-delivery-claude-plugin"]["host"], "claude")
            self.assertEqual(packages["roadmap-delivery-generic-markdown-pack"]["support_status"], "documentation_template")

    def test_manifest_and_checksum_bytes_are_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            first_dir = Path(tmp) / "first"
            second_dir = Path(tmp) / "second"
            self.build_release(first_dir)
            self.build_release(second_dir)

            for filename in (
                f"roadmap-delivery-{VERSION}-manifest.json",
                f"roadmap-delivery-{VERSION}-checksums.sha256",
            ):
                with self.subTest(filename=filename):
                    self.assertEqual(
                        (first_dir / filename).read_bytes(),
                        (second_dir / filename).read_bytes(),
                    )


if __name__ == "__main__":
    unittest.main()
