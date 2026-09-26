"""Filesystem migration checks; never install into the real home directory."""

import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dotfiles-install-test-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.repo = self.base / "source with spaces"
        (self.repo / "scripts").mkdir(parents=True)
        shutil.copy2(ROOT / "scripts/install.py", self.repo / "scripts/install.py")
        (self.repo / ".example").write_text("shared configuration\n")
        (self.repo / "templates/flipper").mkdir(parents=True)
        (self.repo / "templates/tool-versions").write_text("python 3.12.9\n")
        (self.repo / "templates/flipper/settings.json").write_text(json.dumps({
            "jsApps": {"webAppLauncher": {"width": 800, "height": 600}},
        }))
        self.manifest = {
            "version": 1,
            "links": [{"source": ".example", "root": "home", "target": ".example"}],
            "seeds": [
                {"source": "templates/tool-versions", "root": "home", "target": ".tool-versions"},
                {"source": "templates/flipper/settings.json", "root": "config", "target": "flipper/settings.json"},
            ],
        }
        self.write_manifest()
        self.target = self.base / "target home"
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("DOTFILES_")}
        self.env["GIT_OPTIONAL_LOCKS"] = "0"
        self.env["GIT_CONFIG_GLOBAL"] = os.devnull
        self.env["GIT_CONFIG_NOSYSTEM"] = "1"

    def write_manifest(self):
        (self.repo / "install-manifest.json").write_text(json.dumps(self.manifest))

    def run_install(self, *args, success=True):
        result = subprocess.run([
            sys.executable, str(self.repo / "scripts/install.py"),
            "--target-dir", str(self.target), *args,
        ], capture_output=True, text=True, env=self.env, timeout=20)
        self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
        return result

    def test_dry_run_creates_nothing(self):
        self.run_install("--dry-run")
        self.assertFalse(self.target.exists())

    def test_seeds_stay_local_and_repeated_install_preserves_edits(self):
        self.run_install()
        link = self.target / ".example"
        seed = self.target / ".tool-versions"
        self.assertTrue(link.is_symlink())
        self.assertEqual(link.resolve(), (self.repo / ".example").resolve())
        self.assertFalse(seed.is_symlink())
        seed.write_text("python system\n")
        before = (link.lstat().st_ino, seed.stat().st_mtime_ns)
        self.run_install()
        self.assertEqual(seed.read_text(), "python system\n")
        self.assertEqual(before, (link.lstat().st_ino, seed.stat().st_mtime_ns))

    def test_backups_are_unique_and_recover_original_contents(self):
        self.target.mkdir()
        target = self.target / ".example"
        target.write_text("first local configuration\n")
        self.run_install()
        target.unlink()
        target.write_text("second local configuration\n")
        self.run_install()
        root = self.target / ".local/state/dotfiles/backups"
        sessions = list(root.iterdir())
        self.assertEqual(len(sessions), 2)
        saved = set()
        for session in sessions:
            self.assertEqual(session.stat().st_mode & 0o777, 0o700)
            for entry in json.loads((session / "manifest.json").read_text()):
                saved.add((session / entry["contents"]).read_text())
        self.assertEqual(saved, {"first local configuration\n", "second local configuration\n"})

    def test_legacy_seed_symlink_is_detached_without_data_loss(self):
        self.target.mkdir()
        old = self.base / "previous tool versions"
        old.write_text("python system\n")
        seed = self.target / ".tool-versions"
        seed.symlink_to(old)
        self.run_install()
        self.assertFalse(seed.is_symlink())
        self.assertEqual(seed.read_bytes(), old.read_bytes())

    def test_custom_config_destination(self):
        config = self.base / "custom config"
        self.run_install("--config-dir", str(config))
        self.assertTrue((config / "flipper/settings.json").is_file())
        self.assertFalse((self.target / ".config").exists())

    def test_flipper_nested_overrides_preserve_local_state(self):
        target = self.target / ".config/flipper/settings.json"
        target.parent.mkdir(parents=True)
        target.write_text(json.dumps({"_persist": {"version": 1},
                                      "jsApps": {"webAppLauncher": {"width": 123}}}))
        overrides = self.base / "machine.json"
        overrides.write_text(json.dumps({"androidHome": "/opt/tools/android-sdk",
                                        "jsApps": {"webAppLauncher": {"url": "http://localhost:9000"}}}))
        self.run_install("--flipper-overrides", str(overrides))
        data = json.loads(target.read_text())
        self.assertEqual(data["_persist"], {"version": 1})
        self.assertEqual(data["jsApps"]["webAppLauncher"],
                         {"width": 123, "height": 600, "url": "http://localhost:9000"})
        self.assertEqual(data["androidHome"], "/opt/tools/android-sdk")

    def test_bad_override_is_rejected_before_any_installation(self):
        overrides = self.base / "bad.json"
        overrides.write_text("[]")
        self.run_install("--flipper-overrides", str(overrides), success=False)
        self.assertFalse(self.target.exists())

    def test_manifest_traversal_is_rejected_before_any_installation(self):
        self.manifest["links"][0]["target"] = "../outside"
        self.write_manifest()
        self.run_install(success=False)
        self.assertFalse(self.target.exists())
        self.assertFalse((self.base / "outside").exists())

    def test_broken_seed_requires_recovery_instead_of_silent_replacement(self):
        self.target.mkdir()
        seed = self.target / ".tool-versions"
        seed.symlink_to(self.base / "missing-old-source")
        self.run_install(success=False)
        self.assertTrue(seed.is_symlink())
        self.assertFalse((self.target / ".example").exists())

    def test_parent_directory_symlink_cannot_replace_repository_source(self):
        source = self.repo / "shared/config"
        source.parent.mkdir()
        source.write_text("original shared contents\n")
        self.manifest["links"].append({"source": "shared/config", "root": "home", "target": "shared/config"})
        self.write_manifest()
        self.target.mkdir()
        (self.target / "shared").symlink_to(source.parent, target_is_directory=True)
        self.run_install(success=False)
        self.assertFalse(source.is_symlink())
        self.assertEqual(source.read_text(), "original shared contents\n")
        self.assertFalse((self.target / ".example").exists())

    def test_repository_cannot_be_installation_target(self):
        self.run_install("--target-dir", str(self.repo), success=False)
        self.assertFalse((self.repo / ".example").is_symlink())
        self.assertEqual((self.repo / ".example").read_text(), "shared configuration\n")
        self.assertFalse((self.repo / ".local").exists())

    def test_private_output_directories_cannot_be_inside_repository(self):
        for option in ("--config-dir", "--local-dir"):
            with self.subTest(option=option):
                self.run_install(option, str(self.repo / "private-output"), success=False)
                self.assertFalse(self.target.exists())
                self.assertFalse((self.repo / "private-output").exists())

    def test_backup_directory_symlink_cannot_leak_into_repository(self):
        state = self.target / ".local/state"
        state.mkdir(parents=True)
        (state / "dotfiles").symlink_to(self.repo, target_is_directory=True)
        target = self.target / ".example"
        target.write_text("private settings\n")
        self.run_install(success=False)
        self.assertEqual(target.read_text(), "private settings\n")
        self.assertFalse(target.is_symlink())
        self.assertFalse((self.repo / "backups").exists())

    def test_seed_directory_symlink_is_rejected_before_any_writes(self):
        self.target.mkdir()
        directory = self.base / "existing directory"
        directory.mkdir()
        seed = self.target / ".tool-versions"
        seed.symlink_to(directory, target_is_directory=True)
        self.run_install(success=False)
        self.assertTrue(seed.is_symlink())
        self.assertFalse((self.target / ".example").exists())

    @unittest.skipUnless(hasattr(os, "mkfifo"), "requires POSIX named pipes")
    def test_seed_named_pipe_is_rejected_without_opening_it(self):
        self.target.mkdir()
        os.mkfifo(self.target / ".tool-versions")
        self.run_install(success=False)
        self.assertFalse((self.target / ".example").exists())

    def test_existing_leaf_link_remains_supported(self):
        self.target.mkdir()
        target = self.target / ".example"
        target.symlink_to(self.repo / ".example")
        original_inode = target.lstat().st_ino
        self.run_install()
        self.assertEqual(target.lstat().st_ino, original_inode)
        self.assertEqual((self.repo / ".example").read_text(), "shared configuration\n")

    def installer_args(self):
        return type("Args", (), dict(target_dir=str(self.target), config_dir=None,
                                     local_dir=None, render_flipper=False,
                                     flipper_overrides=None, install_hooks=False,
                                     dry_run=True))()

    def test_relative_xdg_directories_are_rejected_when_used(self):
        installer = runpy.run_path(str(self.repo / "scripts/install.py"))["Installer"]
        for name in ("XDG_CONFIG_HOME", "XDG_STATE_HOME"):
            with self.subTest(name=name), mock.patch.dict(os.environ, {
                "XDG_CONFIG_HOME": str(self.base / "xdg-config"),
                "XDG_STATE_HOME": str(self.base / "xdg-state"),
                name: "relative-directory",
            }), mock.patch.object(Path, "home", return_value=self.target):
                # Only the path-discovery API is mocked; HOME is never changed.
                with self.assertRaisesRegex(ValueError, name + " must be an absolute"):
                    installer(self.installer_args())
                self.assertFalse(self.target.exists())

    def test_absolute_xdg_directories_are_used_for_actual_home(self):
        installer = runpy.run_path(str(self.repo / "scripts/install.py"))["Installer"]
        config = self.base / "xdg-config"
        state = self.base / "xdg-state"
        with mock.patch.dict(os.environ, {
            "XDG_CONFIG_HOME": str(config), "XDG_STATE_HOME": str(state),
        }), mock.patch.object(Path, "home", return_value=self.target):
            installation = installer(self.installer_args())
        self.assertEqual(installation.config, config)
        self.assertEqual(installation.backup_root, state / "dotfiles/backups")
        self.assertFalse(config.exists())
        self.assertFalse(state.exists())

    def prepare_git_hooks(self):
        subprocess.run(["git", "init", "--quiet", str(self.repo)], env=self.env, check=True)
        source = self.repo / ".githooks"
        source.mkdir()
        for name in ("pre-commit", "pre-push"):
            (source / name).write_text("#!/bin/sh\nexit 0\n")
        return self.repo / ".git/hooks"

    def test_optional_hooks_back_up_previous_content_and_are_idempotent(self):
        hooks = self.prepare_git_hooks()
        previous = hooks / "pre-commit"
        previous.write_text("#!/bin/sh\nprintf old-hook\n")
        previous.chmod(0o755)
        self.run_install("--install-hooks")
        self.assertEqual(previous.read_text(), "#!/bin/sh\nexit 0\n")
        self.assertEqual(previous.stat().st_mode & 0o777, 0o755)
        backups = list((self.target / ".local/state/dotfiles/backups").iterdir())
        self.assertEqual(len(backups), 1)
        records = json.loads((backups[0] / "manifest.json").read_text())
        saved = [record for record in records
                 if Path(record["destination"]).resolve() == previous.resolve()]
        self.assertEqual(len(saved), 1)
        self.assertEqual((backups[0] / saved[0]["contents"]).read_text(), "#!/bin/sh\nprintf old-hook\n")
        before = (previous.stat().st_ino, previous.stat().st_mtime_ns)
        self.run_install("--install-hooks")
        self.assertEqual(before, (previous.stat().st_ino, previous.stat().st_mtime_ns))
        self.assertEqual(len(list(backups[0].parent.iterdir())), 1)

    def test_custom_hooks_path_is_rejected_before_writes(self):
        self.prepare_git_hooks()
        subprocess.run(["git", "-C", str(self.repo), "config", "core.hooksPath", "custom-hooks"],
                       env=self.env, check=True)
        result = self.run_install("--install-hooks", success=False)
        self.assertIn("core.hooksPath", result.stderr)
        self.assertFalse(self.target.exists())

    def test_dry_run_hooks_and_rendering_create_nothing(self):
        hooks = self.prepare_git_hooks()
        before = {p.name: p.read_bytes() for p in hooks.iterdir() if p.is_file()}
        self.run_install("--dry-run", "--install-hooks", "--render-flipper")
        after = {p.name: p.read_bytes() for p in hooks.iterdir() if p.is_file()}
        self.assertEqual(before, after)
        self.assertFalse(self.target.exists())


if __name__ == "__main__":
    unittest.main()
