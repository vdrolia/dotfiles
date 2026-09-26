"""Privacy gates use isolated repositories and a scanner double, never home files."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

CHECKER = Path(__file__).resolve().parents[1] / "scripts/check-public.py"
GIT = shutil.which("git")


class PublicCheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        scanner = self.bin / "gitleaks"
        scanner.write_text(
            "#!" + sys.executable + "\n"
            "from pathlib import Path\nimport sys\n"
            "files=Path(sys.argv[-1]).rglob('*')\n"
            "if any(p.is_file() and b'credential-fixture' in p.read_bytes() for p in files):\n"
            " print('sensitive-scanner-output'); sys.exit(1)\n"
        )
        scanner.chmod(0o700)
        self.env = dict({key: value for key, value in os.environ.items() if not key.startswith("GIT_")},
                        PATH=str(self.bin) + os.pathsep + os.defpath,
                        GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull,
                        GIT_OPTIONAL_LOCKS="0", GIT_AUTHOR_NAME="Public Contributor",
                        GIT_COMMITTER_NAME="Public Contributor",
                        GIT_AUTHOR_EMAIL="public" + "@" + "example.invalid",
                        GIT_COMMITTER_EMAIL="public" + "@" + "example.invalid",
                        DOTFILES_LOCAL_DIR=str(self.root / "private-settings"))
        self.env.pop("DOTFILES_PRIVACY_DENYLIST", None)
        self.git("init", "-q")
        self.git("config", "user.name", "Public Contributor")
        self.git("config", "user.email", "public" + "@" + "example.invalid")
        self.git("config", "core.hooksPath", str(self.root / "empty-hooks"))
        self.git("config", "commit.gpgsign", "false")
        self.git("config", "tag.gpgsign", "false")

    def git(self, *args):
        return subprocess.check_output([GIT, "-C", str(self.repo), *args], env=self.env).decode().strip()

    def check(self, mode="working-tree", stdin=None, env=None):
        return subprocess.run([sys.executable, str(CHECKER), "--mode", mode],
                              cwd=self.repo, env=env or self.env, input=stdin,
                              capture_output=True, text=True)

    def put(self, name, data):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data)
        return path

    def test_untracked_candidates_and_deleted_files(self):
        old = self.put("claude/knowledge/note.md", "private research")
        self.git("add", ".")
        old.unlink()
        self.put("config.txt", "generic settings")
        self.assertEqual(self.check().returncode, 0)
        self.put("new.txt", "person" + "@" + "private-mail.test")
        self.assertNotEqual(self.check().returncode, 0)

    def test_staged_snapshot_cannot_be_hidden_by_working_tree(self):
        file = self.put("config.txt", "person" + "@" + "private-mail.test")
        self.git("add", ".")
        file.write_text("safe current content")
        result = self.check("staged")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("email", result.stdout)
        self.assertEqual(self.check().returncode, 0)

    def test_missing_scanner_fails_closed(self):
        self.put("safe.txt", "safe")
        env = dict(self.env, PATH=str(self.root / "missing"))
        # Locate git explicitly through a wrapper so only the scanner is absent.
        empty_bin = self.root / "git-only"
        empty_bin.mkdir()
        (empty_bin / "git").symlink_to(GIT)
        env["PATH"] = str(empty_bin)
        result = self.check(env=env)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("gitleaks", result.stdout)

    def test_private_denylist_scans_names_and_redacts_output(self):
        marker = "nonpublic-project-marker"
        denylist = self.root / "denylist"
        denylist.write_text(marker + "\n")
        self.put(marker + ".txt", "safe body")
        result = self.check(env=dict(self.env, DOTFILES_PRIVACY_DENYLIST=str(denylist)))
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn(marker, result.stdout + result.stderr)

    def test_denylist_must_resolve_outside_checkout(self):
        inside = self.put("hidden-list.txt", "private-test-marker\n")
        external_link = self.root / "external-link"
        external_link.symlink_to(inside)
        for configured in [inside, external_link]:
            with self.subTest(configured=configured.name):
                result = self.check(env=dict(self.env, DOTFILES_PRIVACY_DENYLIST=str(configured)))
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("must resolve outside", result.stdout)
                self.assertNotIn("private-test-marker", result.stdout + result.stderr)

    def test_default_denylist_uses_private_local_or_xdg_directory(self):
        marker = "personal-test-marker"
        self.put("config.txt", marker)
        for source in ["local", "xdg"]:
            with self.subTest(source=source):
                env = dict(self.env)
                if source == "local":
                    directory = Path(env["DOTFILES_LOCAL_DIR"])
                else:
                    env.pop("DOTFILES_LOCAL_DIR")
                    env["XDG_CONFIG_HOME"] = str(self.root / "config-root")
                    directory = Path(env["XDG_CONFIG_HOME"]) / "dotfiles"
                directory.mkdir(parents=True)
                (directory / "privacy-denylist.txt").write_text(marker + "\n")
                result = self.check(env=env)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("private denylist match", result.stdout)
                self.assertNotIn(marker, result.stdout + result.stderr)

    def test_explicit_missing_denylist_fails_closed(self):
        result = self.check(env=dict(self.env, DOTFILES_PRIVACY_DENYLIST=str(self.root / "missing")))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("denylist could not be read", result.stdout)

    def test_force_added_private_overlays_are_blocked(self):
        paths = ["private/notes.txt", "local/settings.txt", ".config/dotfiles/env.zsh",
                 ".config/nvim/local.lua", ".config/nvim/lua/config/local.lua",
                 "nested/settings.local.json"]
        self.put(".gitignore", "\n".join(paths) + "\n")
        for name in paths:
            with self.subTest(name=name):
                path = self.put(name, "ordinary settings")
                self.git("add", "--force", "--", name)
                result = self.check("staged")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("prohibited private path", result.stdout)
                self.git("rm", "--cached", "--force", "--", name)
                path.unlink()

    def test_public_overlay_examples_remain_allowed(self):
        for name in ["examples/vimrc.local.example", "examples/tmux.conf.local.example",
                     "examples/nvim.lua.example", "examples/gitconfig.local.example",
                     ".env.example"]:
            self.put(name, "generic template")
        self.assertEqual(self.check().returncode, 0)

    def test_scanner_output_is_never_echoed(self):
        self.put("config.txt", "credential-fixture")
        result = self.check()
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("sensitive-scanner-output", result.stdout + result.stderr)

    def test_paths_ips_and_prohibited_files(self):
        for name, content in [
            ("config.txt", "/" + "home/" + "sample-person/private"),
            ("config.txt", ".".join(["192", "168", "23", "7"])),
            ("config.txt", ".".join(["100", "64", "23", "7"])),
            ("config.txt", ".".join(["100", "127", "23", "7"])),
            ("config.txt", "fd" + "00::1"),
            (".env", "SETTING=value"),
        ]:
            with self.subTest(name=name, content=content):
                path = self.put(name, content)
                self.assertNotEqual(self.check().returncode, 0)
                path.unlink()

    def test_dependency_urls_schema_and_example_email_pass(self):
        self.put("config.json", '{"$schema":"https://example.org/schema.json",'
                 '"plugin":"owner/public-plugin","email":"public' + '@example.invalid"}')
        self.put("dependencies.txt", "git" + "@" + "github.com:owner/public-repo\n")
        self.assertEqual(self.check().returncode, 0)

    def test_credentials_in_filenames_are_scanned(self):
        self.put("credential-fixture.txt", "person" + "@" + "private-mail.test")
        result = self.check()
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("credential-fixture", result.stdout + result.stderr)

    def test_public_git_email_without_url_context_is_not_exempt(self):
        self.put("settings.txt", "git" + "@" + "github.com")
        self.assertNotEqual(self.check().returncode, 0)

    def test_push_checks_commit_and_annotated_tag_metadata(self):
        self.put("safe.txt", "safe")
        self.git("add", ".")
        self.git("commit", "-qm", "credential-fixture")
        tip = self.git("rev-parse", "HEAD")
        zero = "0" * len(tip)
        self.assertNotEqual(self.check("pre-push", f"refs/heads/main {tip} refs/heads/main {zero}\n").returncode, 0)
        self.git("tag", "-a", "release", "-m", "credential-fixture")
        tag = self.git("rev-parse", "release")
        # The commit itself is already on the remote; the newly sent tag must be checked.
        self.assertNotEqual(self.check("pre-push", f"refs/tags/release {tag} refs/tags/release {tip}\n").returncode, 0)

    def test_push_checks_removed_secrets_in_intermediate_commits(self):
        file = self.put("config.txt", "safe")
        self.git("add", ".")
        self.git("commit", "-qm", "Initial")
        base = self.git("rev-parse", "HEAD")
        file.write_text("credential-fixture")
        self.git("commit", "-qam", "Intermediate")
        file.write_text("safe again")
        self.git("commit", "-qam", "Clean tip")
        tip = self.git("rev-parse", "HEAD")
        result = self.check("pre-push", f"refs/heads/main {tip} refs/heads/main {base}\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("credential", result.stdout)

    def test_new_ref_checks_full_history_and_deletions_need_no_scan(self):
        self.put("safe.txt", "safe")
        self.git("add", ".")
        self.git("commit", "-qm", "Initial")
        tip = self.git("rev-parse", "HEAD")
        zero = "0" * len(tip)
        self.assertEqual(self.check("pre-push", f"refs/heads/main {tip} refs/heads/main {zero}\n").returncode, 0)
        self.assertEqual(self.check("pre-push", f"(delete) {zero} refs/heads/main {tip}\n").returncode, 0)


if __name__ == "__main__":
    unittest.main()
