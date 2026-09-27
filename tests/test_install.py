"""Filesystem migration checks; never install into the real home directory."""

import json
import os
from pathlib import Path
import runpy
import shlex
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
            "version": 2,
            "links": [{"source": ".example", "root": "home", "target": ".example", "component": "ack"}],
            "seeds": [
                {"source": "templates/tool-versions", "root": "home", "target": ".tool-versions", "component": "tools"},
                {"source": "templates/flipper/settings.json", "root": "config", "target": "flipper/settings.json", "component": "flipper"},
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
            "--target-dir", str(self.target), "--mode", "link", *args,
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
        self.manifest["links"].append({"source": "shared/config", "root": "home", "target": "shared/config", "component": "ack"})
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
                                     enable_auto_sync=False, disable_auto_sync=False,
                                     mode="link", components="all", zsh_dir=None,
                                     git_config=None, vim_config=None, tmux_config=None,
                                     nvim_profile="dotfiles-nvim",
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
        for name in ("pre-commit", "pre-push", "post-commit"):
            (source / name).write_text("#!/bin/sh\nexit 0\n")
        return self.repo / ".git/hooks"

    def local_auto_sync(self):
        return subprocess.run(["git", "-C", str(self.repo), "config", "--local",
                               "--get-all", "dotfiles.autoSync"], env=self.env,
                              capture_output=True, text=True)

    def test_normal_install_and_privacy_hooks_do_not_enable_auto_sync(self):
        hooks = self.prepare_git_hooks()
        before = (self.repo / ".git/config").read_bytes()
        self.run_install()
        self.assertFalse((hooks / "post-commit").exists())
        self.assertFalse((hooks / "pre-push").exists())
        self.assertEqual(self.local_auto_sync().returncode, 1)
        self.run_install("--install-hooks")
        self.assertTrue((hooks / "pre-push").is_file())
        self.assertFalse((hooks / "post-commit").exists())
        self.assertEqual((self.repo / ".git/config").read_bytes(), before)

    def test_explicit_auto_sync_installs_all_hooks_and_backs_up_old_post_commit(self):
        hooks = self.prepare_git_hooks()
        previous = hooks / "post-commit"
        previous.write_text("#!/bin/sh\nprintf old-post-commit\n")
        previous.chmod(0o755)
        self.run_install("--enable-auto-sync")
        self.assertEqual(self.local_auto_sync().stdout, "true\n")
        for name in ("pre-commit", "pre-push", "post-commit"):
            self.assertEqual((hooks / name).read_bytes(), (self.repo / ".githooks" / name).read_bytes())
            self.assertEqual((hooks / name).stat().st_mode & 0o777, 0o755)
        sessions = list((self.target / ".local/state/dotfiles/backups").iterdir())
        self.assertEqual(len(sessions), 1)
        records = json.loads((sessions[0] / "manifest.json").read_text())
        saved = [record for record in records if Path(record["destination"]).resolve() == previous.resolve()]
        self.assertEqual(len(saved), 1)
        self.assertEqual((sessions[0] / saved[0]["contents"]).read_text(),
                         "#!/bin/sh\nprintf old-post-commit\n")
        config = self.repo / ".git/config"
        before = (previous.stat().st_ino, config.stat().st_mtime_ns)
        self.run_install("--enable-auto-sync")
        self.assertEqual(before, (previous.stat().st_ino, config.stat().st_mtime_ns))
        self.assertEqual(len(list(sessions[0].parent.iterdir())), 1)
        self.run_install()
        self.assertEqual(self.local_auto_sync().stdout, "true\n")

    def test_disable_auto_sync_preserves_hooks_even_with_custom_hooks_path(self):
        hooks = self.prepare_git_hooks()
        self.run_install("--enable-auto-sync")
        custom = self.base / "custom hooks"
        custom.mkdir()
        (custom / "post-commit").write_text("#!/bin/sh\nprintf unrelated-hook\n")
        subprocess.run(["git", "-C", str(self.repo), "config", "core.hooksPath", str(custom)],
                       env=self.env, check=True)
        before = {str(p): p.read_bytes() for directory in (hooks, custom)
                  for p in directory.iterdir() if p.is_file()}
        self.run_install("--disable-auto-sync")
        self.assertEqual(self.local_auto_sync().stdout, "false\n")
        after = {str(p): p.read_bytes() for directory in (hooks, custom)
                 for p in directory.iterdir() if p.is_file()}
        self.assertEqual(before, after)
        config = self.repo / ".git/config"
        mtime = config.stat().st_mtime_ns
        self.run_install("--disable-auto-sync")
        self.assertEqual(mtime, config.stat().st_mtime_ns)

    def test_auto_sync_dry_run_never_changes_hooks_config_or_targets(self):
        hooks = self.prepare_git_hooks()
        before = {p.name: p.read_bytes() for p in hooks.iterdir() if p.is_file()}
        config_before = (self.repo / ".git/config").read_bytes()
        for option in ("--enable-auto-sync", "--disable-auto-sync"):
            with self.subTest(option=option):
                self.run_install(option, "--dry-run")
                self.assertEqual(config_before, (self.repo / ".git/config").read_bytes())
                self.assertEqual(before, {p.name: p.read_bytes() for p in hooks.iterdir() if p.is_file()})
                self.assertFalse(self.target.exists())

    def test_auto_sync_conflicting_flags_fail_before_any_writes(self):
        self.prepare_git_hooks()
        before = (self.repo / ".git/config").read_bytes()
        self.run_install("--enable-auto-sync", "--disable-auto-sync", success=False)
        self.assertFalse(self.target.exists())
        self.assertEqual(before, (self.repo / ".git/config").read_bytes())

    def test_auto_sync_hook_preflight_failure_cannot_enable_or_partially_install(self):
        hooks = self.prepare_git_hooks()
        (hooks / "post-commit").mkdir()
        self.run_install("--enable-auto-sync", success=False)
        self.assertEqual(self.local_auto_sync().returncode, 1)
        self.assertFalse((hooks / "pre-push").exists())
        self.assertFalse(self.target.exists())

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
        before = (self.repo / ".git/config").read_bytes()
        for option in ("--install-hooks", "--enable-auto-sync"):
            with self.subTest(option=option):
                result = self.run_install(option, success=False)
                self.assertIn("core.hooksPath", result.stderr)
                self.assertFalse(self.target.exists())
                self.assertEqual(before, (self.repo / ".git/config").read_bytes())

    def test_dry_run_hooks_and_rendering_create_nothing(self):
        hooks = self.prepare_git_hooks()
        before = {p.name: p.read_bytes() for p in hooks.iterdir() if p.is_file()}
        self.run_install("--dry-run", "--install-hooks", "--render-flipper")
        after = {p.name: p.read_bytes() for p in hooks.iterdir() if p.is_file()}
        self.assertEqual(before, after)
        self.assertFalse(self.target.exists())


class ModularInstallerTests(unittest.TestCase):
    write_manifest = InstallerTests.write_manifest

    def setUp(self):
        InstallerTests.setUp(self)
        quoted_checkout = self.base / ("modules ' \" $ literal [*?] " + "\\" + " backslash")
        self.repo.rename(quoted_checkout)
        self.repo = quoted_checkout
        sources = {
            ".zshrc": 'typeset -g DOTFILES_TEST_ORDER="${DOTFILES_TEST_ORDER:-}shared"\n'
                      'typeset -g DOTFILES_TEST_FRAMEWORKS="${DOTFILES_ZSH_FRAMEWORKS-unset}"\n',
            ".zshrc-functions": "# Shared helper fixture\n",
            ".gitconfig": "[demo]\n  value = shared\n",
            ".vimrc": "let g:shared_coexist = get(g:, 'dotfiles_coexist', 0)\nset tabstop=2\n",
            ".tmux.conf": 'set -gF @shared_coexist "#{@dotfiles_coexist}"\nset -g status-left shared\n',
            ".ackrc": "--smart-case\n",
            ".config/nvim/init.lua": "-- profile fixture\n",
            ".config/nvim/lazy-lock.json": "{}\n",
            ".config/nvim/lua/config/example.lua": "return {}\n",
        }
        components = {".zshrc": "zsh", ".zshrc-functions": "zsh", ".gitconfig": "git",
                      ".vimrc": "vim", ".tmux.conf": "tmux", ".ackrc": "ack"}
        self.manifest["links"] = []
        for name, data in sources.items():
            source = self.repo / name
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text(data)
            nvim = name.startswith(".config/")
            self.manifest["links"].append({"source": name, "root": "config" if nvim else "home",
                                            "target": name.removeprefix(".config/") if nvim else name,
                                            "component": "nvim" if nvim else components[name]})
        self.write_manifest()

    def run_install(self, *args, success=True):
        result = subprocess.run([sys.executable, str(self.repo / "scripts/install.py"),
                                 "--target-dir", str(self.target), *args],
                                capture_output=True, text=True, env=self.env, timeout=20)
        self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
        return result

    def run_zsh(self, destination):
        return subprocess.run([shutil.which("zsh"), "-dfc", "source " + shlex.quote(str(destination)) +
                               '\nprint -r -- "$DOTFILES_TEST_ORDER:$DOTFILES_TEST_FRAMEWORKS:${DOTFILES_ZSH_FRAMEWORKS-unset}"'],
                              env=self.env, capture_output=True, text=True, timeout=10)

    def git_value(self, path, key):
        return subprocess.check_output(["git", "config", "--file", str(path), "--includes", "--get", key],
                                       env=self.env, text=True).strip()

    def test_default_composes_preserves_existing_bytes_and_is_idempotent(self):
        self.target.mkdir()
        originals = {".zshrc": b'DOTFILES_TEST_ORDER="${DOTFILES_TEST_ORDER}:existing"\n',
                     ".gitconfig": b"[demo]\n  value = existing\n",
                     ".vimrc": b"set tabstop=7\n", ".tmux.conf": b"set -g status-left existing\n"}
        for name, data in originals.items():
            (self.target / name).write_bytes(data)
        self.run_install("--components", "zsh,git,vim,tmux")
        for name, data in originals.items():
            self.assertFalse((self.target / name).is_symlink())
            self.assertTrue((self.target / name).read_bytes().endswith(data))
        self.assertFalse((self.target / ".zshrc-functions").exists())
        self.assertEqual(self.git_value(self.target / ".gitconfig", "demo.value"), "existing")
        before = {name: ((self.target / name).read_bytes(), (self.target / name).stat().st_ino)
                  for name in originals}
        self.run_install("--components", "zsh,git,vim,tmux")
        self.assertEqual(before, {name: ((self.target / name).read_bytes(), (self.target / name).stat().st_ino)
                                 for name in originals})
        backups = list((self.target / ".local/state/dotfiles/backups").iterdir())
        self.assertEqual(len(backups), 1)

    @unittest.skipUnless(shutil.which("zsh"), "zsh is required")
    def test_foreign_shell_symlink_sources_original_without_modifying_it(self):
        foreign = self.base / "other dotfiles"
        foreign.mkdir()
        original = foreign / "shell config"
        original.write_text('DOTFILES_TEST_ORDER="${DOTFILES_TEST_ORDER}:foreign"\n')
        subprocess.run(["git", "init", "-q", str(foreign)], env=self.env, check=True)
        self.target.mkdir()
        destination = self.target / ".zshrc"
        destination.symlink_to(original)
        before = (original.read_bytes(), original.stat().st_ino)
        self.run_install("--components", "zsh")
        self.assertFalse(destination.is_symlink())
        self.assertEqual(before, (original.read_bytes(), original.stat().st_ino))
        result = self.run_zsh(destination)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "shared:foreign:0:unset\n")
        original.write_text('DOTFILES_TEST_ORDER="${DOTFILES_TEST_ORDER}:updated"\n')
        self.assertEqual(self.run_zsh(destination).stdout, "shared:updated:0:unset\n")

    def test_foreign_parent_directory_symlink_fails_before_any_changes(self):
        foreign = self.base / "other dotfiles"
        foreign.mkdir()
        subprocess.run(["git", "init", "-q", str(foreign)], env=self.env, check=True)
        self.target.mkdir()
        (self.target / ".config").symlink_to(foreign)
        self.run_install("--components", "zsh,nvim", success=False)
        self.assertFalse((self.target / ".zshrc").exists())
        self.assertFalse((foreign / "dotfiles-nvim").exists())

    def test_backups_cannot_copy_private_contents_into_a_foreign_checkout(self):
        foreign = self.base / "other dotfiles"
        foreign.mkdir()
        subprocess.run(["git", "init", "-q", str(foreign)], env=self.env, check=True)
        state = self.target / ".local/state"
        state.mkdir(parents=True)
        (state / "dotfiles").symlink_to(foreign)
        existing = self.target / ".zshrc"
        existing.write_text("# private original settings\n")
        self.run_install("--components", "zsh", success=False)
        self.assertEqual(existing.read_text(), "# private original settings\n")
        self.assertFalse((foreign / "backups").exists())

    def test_owned_symlinks_become_standalone_loaders_and_keep_private_identity(self):
        self.target.mkdir()
        for name in (".zshrc", ".gitconfig", ".vimrc", ".tmux.conf"):
            (self.target / name).symlink_to(self.repo / name)
        local = self.target / ".gitconfig.local"
        local.write_text("[user]\n  name = Local Contributor\n")
        self.run_install("--components", "zsh,git,vim,tmux")
        for name in (".zshrc", ".gitconfig", ".vimrc", ".tmux.conf"):
            path = self.target / name
            self.assertFalse(path.is_symlink())
            self.assertIn("load mode: standalone", path.read_text())
            with path.open("a") as stream:
                stream.write(('"' if name == ".vimrc" else "#") + " local customization\n")
        self.run_install("--components", "zsh,git,vim,tmux")
        for name in (".zshrc", ".gitconfig", ".vimrc", ".tmux.conf"):
            self.assertIn("load mode: standalone", (self.target / name).read_text())
        self.assertEqual(self.git_value(self.target / ".gitconfig", "user.name"), "Local Contributor")

    def test_native_xdg_git_and_tmux_are_used_without_home_shadow_files(self):
        config = self.base / "config root"
        for name in ("git/config", "tmux/tmux.conf"):
            path = config / name
            path.parent.mkdir(parents=True)
            path.write_text("# existing\n")
        self.run_install("--components", "git,tmux", "--config-dir", str(config))
        self.assertFalse((self.target / ".gitconfig").exists())
        self.assertFalse((self.target / ".tmux.conf").exists())
        self.assertIn("dotfiles managed git", (config / "git/config").read_text())
        self.assertIn("dotfiles managed tmux", (config / "tmux/tmux.conf").read_text())

    def test_existing_xdg_git_is_modified_before_later_home_global(self):
        config = self.target / ".config/git/config"
        config.parent.mkdir(parents=True)
        config.write_text("[demo]\n value = xdg\n")
        home = self.target / ".gitconfig"
        home.write_text("[demo]\n value = home\n")
        self.run_install("--components", "git")
        self.assertEqual(home.read_text(), "[demo]\n value = home\n")
        self.assertEqual(self.git_value(config, "demo.value"), "xdg")

    def test_real_home_discovery_honors_zdotdir_and_explicit_git_environment(self):
        installer = runpy.run_path(str(self.repo / "scripts/install.py"))["Installer"]
        args = InstallerTests.installer_args(self)
        args.mode = "modular"
        args.components = "zsh,git"
        zsh = self.base / "zsh startup"
        git_config = self.base / "global git config"
        with mock.patch.dict(os.environ, {"ZDOTDIR": str(zsh), "GIT_CONFIG_GLOBAL": str(git_config),
                                          "XDG_CONFIG_HOME": str(self.base / "config"),
                                          "XDG_STATE_HOME": str(self.base / "state")}), \
                mock.patch.object(Path, "home", return_value=self.target):
            installation = installer(args)
        self.assertEqual(installation.entrypoints["zsh"], zsh / ".zshrc")
        self.assertEqual(installation.entrypoints["git"], git_config)
        self.assertFalse(self.target.exists())

    def test_nonlayerable_existing_symlinks_and_contents_stay_unchanged(self):
        self.target.mkdir()
        own = self.target / ".ackrc"
        own.symlink_to(self.repo / ".ackrc")
        original = self.base / "tool versions"
        original.write_text("python system\n")
        tools = self.target / ".tool-versions"
        tools.symlink_to(original)
        before = (own.lstat().st_ino, tools.lstat().st_ino, original.read_bytes())
        self.run_install("--components", "ack,tools")
        self.assertEqual(before, (own.lstat().st_ino, tools.lstat().st_ino, original.read_bytes()))
        self.assertTrue(own.is_symlink())
        self.assertTrue(tools.is_symlink())

    def test_component_selection_dry_run_and_invalid_selection(self):
        self.run_install("--components", "zsh", "--dry-run")
        self.assertFalse(self.target.exists())
        self.run_install("--components", "not-a-component", success=False)
        self.assertFalse(self.target.exists())
        self.run_install("--components", "none")
        self.assertFalse(self.target.exists())
        self.run_install("--components", "zsh")
        self.assertTrue((self.target / ".zshrc").is_file())
        self.assertFalse((self.target / ".gitconfig").exists())
        self.assertFalse((self.target / ".config").exists())

    def test_bom_or_binary_config_requires_manual_integration_before_writes(self):
        self.target.mkdir()
        path = self.target / ".gitconfig"
        for data in (b"\xef\xbb\xbf[demo]\n value = existing\n", b"binary\0contents"):
            with self.subTest(data=data):
                path.write_bytes(data)
                result = self.run_install("--components", "zsh,git", success=False)
                self.assertIn("native include manually", result.stderr)
                self.assertEqual(path.read_bytes(), data)
                self.assertFalse((self.target / ".zshrc").exists())

    def test_explicit_link_mode_keeps_git_as_native_wrapper(self):
        self.run_install("--mode", "link", "--components", "zsh,git")
        self.assertTrue((self.target / ".zshrc").is_symlink())
        self.assertTrue((self.target / ".zshrc-functions").is_symlink())
        self.assertFalse((self.target / ".gitconfig").is_symlink())
        self.assertIn(".gitconfig.local", (self.target / ".gitconfig").read_text())

    def test_profile_and_launcher_are_separate_and_lock_is_mutable_local_copy(self):
        existing = self.target / ".config/nvim/init.lua"
        existing.parent.mkdir(parents=True)
        existing.write_text("-- existing unrelated setup\n")
        self.run_install("--components", "nvim", "--nvim-profile", "custom-nvim")
        profile = self.target / ".config/custom-nvim"
        self.assertTrue((profile / "init.lua").is_symlink())
        lock = profile / "lazy-lock.json"
        self.assertFalse(lock.is_symlink())
        lock.write_text('{"private-plugin": {}}\n')
        self.run_install("--components", "nvim", "--nvim-profile", "custom-nvim")
        self.assertEqual(lock.read_text(), '{"private-plugin": {}}\n')
        self.assertEqual(existing.read_text(), "-- existing unrelated setup\n")
        self.assertTrue((self.target / ".local/bin/custom-nvim").is_file())
        self.assertFalse((self.target / ".local/bin/dotfiles-nvim").exists())

    def test_profile_conflicts_and_unsafe_names_fail_before_any_writes(self):
        profile = self.target / ".config/dotfiles-nvim"
        profile.mkdir(parents=True)
        (profile / "init.lua").write_text("-- unrelated\n")
        self.run_install("--components", "zsh,nvim", success=False)
        self.assertFalse((self.target / ".zshrc").exists())
        for name in ("nvim", "../outside", "contains space"):
            self.run_install("--components", "zsh,nvim", "--nvim-profile", name, success=False)
            self.assertFalse((self.target / ".zshrc").exists())

    def test_owned_profile_retargets_broken_links_after_checkout_move(self):
        self.run_install("--components", "zsh,nvim")
        moved = self.base / "moved checkout"
        self.repo.rename(moved)
        self.repo = moved
        profile = self.target / ".config/dotfiles-nvim"
        self.assertFalse((profile / "init.lua").exists())
        self.run_install("--components", "zsh,nvim")
        self.assertEqual((profile / "init.lua").resolve(), (moved / ".config/nvim/init.lua").resolve())
        self.assertIn(str(moved), (self.target / ".zshrc").read_text())
        self.assertFalse((profile / "lazy-lock.json").is_symlink())

    @unittest.skipUnless(shutil.which("zsh"), "zsh is required")
    def test_checkout_quotes_custom_zsh_directory_and_launcher_arguments(self):
        renamed = self.base / "checkout with ' quote $ literal"
        self.repo.rename(renamed)
        self.repo = renamed
        zsh_dir = self.base / "zsh config ' quoted"
        zsh_dir.mkdir()
        (zsh_dir / ".zshrc").write_text('DOTFILES_TEST_ORDER="${DOTFILES_TEST_ORDER}:existing"\n')
        config = self.base / "xdg ' quoted"
        self.run_install("--components", "zsh,nvim", "--zsh-dir", str(zsh_dir), "--config-dir", str(config))
        self.assertEqual(self.run_zsh(zsh_dir / ".zshrc").stdout, "shared:existing:0:unset\n")
        self.assertFalse((self.target / ".zshrc").exists())
        binary = self.base / "bin"
        binary.mkdir()
        nvim = binary / "nvim"
        nvim.write_text('#!/bin/sh\nprintf "%s\\n" "$NVIM_APPNAME" "$XDG_CONFIG_HOME" "$DOTFILES_LOCAL_DIR" "$DOTFILES_NVIM_LOCAL" "$@"\n')
        nvim.chmod(0o700)
        env = dict(self.env, PATH=str(binary) + os.pathsep + os.defpath,
                   DOTFILES_LOCAL_DIR=str(self.base / "explicit local"), DOTFILES_NVIM_LOCAL="explicit-file")
        launcher = self.target / ".local/bin/dotfiles-nvim"
        result = subprocess.run([str(launcher), "file with spaces", "literal$argument"], env=env,
                                capture_output=True, text=True, check=True)
        self.assertEqual(result.stdout.splitlines(), ["dotfiles-nvim", str(config), env["DOTFILES_LOCAL_DIR"],
                                                     "explicit-file", "file with spaces", "literal$argument"])

    @unittest.skipUnless(shutil.which("vim"), "Vim is required")
    def test_native_vim_loader_preserves_existing_settings_and_restores_marker(self):
        self.target.mkdir()
        config = self.target / ".vimrc"
        config.write_text("set tabstop=7\n")
        self.run_install("--components", "vim")
        output = self.base / "vim-output"
        expression = "call writefile([string(&tabstop), string(g:shared_coexist), string(exists('g:dotfiles_coexist'))], " + repr(str(output)) + ")"
        result = subprocess.run([shutil.which("vim"), "-Nu", str(config), "--noplugin", "-n", "-es", "-i", "NONE",
                                 "-c", expression, "-c", "qa!"], env=self.env, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output.read_text().splitlines(), ["7", "1", "0"])

    @unittest.skipUnless(shutil.which("tmux"), "tmux is required")
    def test_native_tmux_loader_restores_marker_and_existing_settings(self):
        self.target.mkdir()
        config = self.target / ".tmux.conf"
        config.write_text("set -g status-left existing\n")
        # An unescaped source-file glob could silently select this other tree.
        decoy = self.base / self.repo.name.replace("[*?]", "*").replace("\\", "")
        decoy.mkdir()
        (decoy / ".tmux.conf").write_text("set -g @unexpected_source loaded\n")
        self.run_install("--components", "tmux")
        socket = str(self.base / "tmux.sock")
        tmux = shutil.which("tmux")
        env = dict(self.env)
        env.pop("TMUX", None)
        env.pop("TMUX_PANE", None)
        command = [tmux, "-S", socket]
        try:
            result = subprocess.run([*command, "-f", str(config), "new-session", "-d", "-s", "fixture", "sleep 30"],
                                    env=env, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            def option(name):
                return subprocess.check_output([*command, "show-options", "-gqv", name], env=env, text=True).strip()
            self.assertEqual(option("status-left"), "existing")
            self.assertEqual(option("@shared_coexist"), "1")
            self.assertEqual(option("@dotfiles_coexist"), "")
            self.assertEqual(option("@unexpected_source"), "")
        finally:
            subprocess.run([*command, "kill-server"], env=env, capture_output=True)


if __name__ == "__main__":
    unittest.main()
