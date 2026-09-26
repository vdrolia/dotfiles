"""Optional sync uses isolated Git repositories and a local bare destination."""
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / ".githooks/post-commit"
GIT = shutil.which("git")


class SyncHookTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.remote = self.root / "destination.git"
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.log = self.root / "network-commands.jsonl"
        self.hooks = self.root / "hooks"
        self.hooks.mkdir()
        wrapper = self.bin / "git"
        wrapper.write_text(
            "#!" + sys.executable + "\n"
            "import json, os, sys\nfrom pathlib import Path\n"
            "args=sys.argv[1:]\n"
            "if any(a in {'push', 'fetch', 'pull', 'ls-remote'} for a in args):\n"
            " with Path(os.environ['SYNC_TEST_LOG']).open('a') as out: out.write(json.dumps(args)+'\\n')\n"
            " if os.environ.get('SYNC_TEST_REJECT_PUSH') and 'push' in args:\n"
            "  print('private-transport-output', file=sys.stderr); sys.exit(1)\n"
            "os.execv(" + repr(GIT) + ", [" + repr(GIT) + "]+args)\n"
        )
        wrapper.chmod(0o700)
        scanner = self.bin / "gitleaks"
        scanner.write_text(
            "#!" + sys.executable + "\n"
            "from pathlib import Path\nimport sys\n"
            "if any(p.is_file() and b'credential-fixture' in p.read_bytes() for p in Path(sys.argv[-1]).rglob('*')):\n"
            " sys.exit(1)\n"
        )
        scanner.chmod(0o700)
        (self.bin / "python3").symlink_to(sys.executable)
        self.env = dict({key: value for key, value in os.environ.items() if not key.startswith("GIT_")},
                        PATH=str(self.bin) + os.pathsep + os.defpath,
                        GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull,
                        GIT_OPTIONAL_LOCKS="0", GIT_AUTHOR_NAME="Public Contributor",
                        GIT_COMMITTER_NAME="Public Contributor",
                        GIT_AUTHOR_EMAIL="public" + "@" + "example.invalid",
                        GIT_COMMITTER_EMAIL="public" + "@" + "example.invalid",
                        DOTFILES_LOCAL_DIR=str(self.root / "private-settings"),
                        SYNC_TEST_LOG=str(self.log))
        for key in ["DOTFILES_PRIVACY_DENYLIST", "DOTFILES_PUBLIC_IDENTITIES", "SYNC_TEST_REJECT_PUSH"]:
            self.env.pop(key, None)
        self.git("init", "-q", "-b", "main")
        self.git("config", "core.hooksPath", str(self.hooks))
        self.git("config", "commit.gpgsign", "false")
        self.git("config", "tag.gpgsign", "false")
        subprocess.run([GIT, "init", "--bare", "-q", str(self.remote)], env=self.env, check=True)
        self.git("remote", "add", "origin", str(self.remote))
        self.git("config", "branch.main.remote", "origin")
        self.git("config", "branch.main.merge", "refs/heads/main")
        scripts = self.repo / "scripts"
        scripts.mkdir()
        shutil.copyfile(ROOT / "scripts/check-public.py", scripts / "check-public.py")
        self.commit("Initial", "ordinary configuration\n")

    def git(self, *args, check=True):
        result = subprocess.run([GIT, "-C", str(self.repo), *args], env=self.env,
                                capture_output=True, text=True, check=check)
        return result.stdout.strip() if check else result

    def commit(self, message, contents):
        (self.repo / "safe.txt").write_text(contents)
        self.git("add", "safe.txt")
        return self.git("commit", "-qm", message, check=False)

    def run_hook(self):
        return subprocess.run(["/bin/sh", str(HOOK)], cwd=self.repo, env=self.env,
                              capture_output=True, text=True)

    def network_commands(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def remote_tip(self):
        return subprocess.run([GIT, "--git-dir", str(self.remote), "rev-parse", "--verify", "refs/heads/main"],
                              env=self.env, capture_output=True, text=True)

    def test_default_disabled_malformed_and_global_enablement_do_not_connect(self):
        global_config = self.root / "global.gitconfig"
        global_config.write_text("[dotfiles]\n\tautoSync = true\n")
        self.env["GIT_CONFIG_GLOBAL"] = str(global_config)
        for value in [None, "false", "invalid"]:
            with self.subTest(value=value):
                if value is not None:
                    self.git("config", "dotfiles.autoSync", value)
                result = self.run_hook()
                self.assertEqual(result.returncode, 0)
                self.assertEqual(self.network_commands(), [])
                self.assertNotEqual(self.remote_tip().returncode, 0)

    def test_enabled_commit_pushes_only_pinned_branch_without_other_hooks(self):
        self.git("config", "dotfiles.autoSync", "true")
        self.git("config", "push.followTags", "true")
        self.git("config", "push.recurseSubmodules", "on-demand")
        self.git("config", "remote.origin.mirror", "true")
        self.git("config", "remote.origin.push", "refs/heads/extra:refs/heads/extra")
        self.git("branch", "extra")
        self.git("tag", "-a", "release", "-m", "Release")
        # Git prepends its own executable directory when launching hooks. Keep
        # the test wrapper first so transport calls remain observable here.
        (self.hooks / "post-commit").write_text(
            "#!/bin/sh\nPATH=" + shlex.quote(self.env["PATH"]) + "\nexport PATH\n"
            "exec /bin/sh " + shlex.quote(str(HOOK)) + "\n"
        )
        (self.hooks / "post-commit").chmod(0o700)
        result = self.commit("Update", "updated ordinary configuration\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        tip = self.git("rev-parse", "HEAD")
        self.assertEqual(self.remote_tip().stdout.strip(), tip)
        refs = subprocess.check_output([GIT, "--git-dir", str(self.remote), "for-each-ref", "--format=%(refname)"], env=self.env).decode().splitlines()
        self.assertEqual(refs, ["refs/heads/main"])
        commands = self.network_commands()
        self.assertEqual(len(commands), 1)
        self.assertEqual(commands[0][-2:], ["origin", tip + ":refs/heads/main"])
        for option in ["--no-force", "--no-follow-tags", "--recurse-submodules=no"]:
            self.assertIn(option, commands[0])
        self.assertNotIn("--no-verify", commands[0])

    def test_privacy_failure_and_missing_scanner_prevent_connection(self):
        self.git("config", "dotfiles.autoSync", "true")
        self.commit("Sensitive fixture", "credential-fixture\n")
        result = self.run_hook()
        self.assertEqual(result.returncode, 0)
        self.assertIn("commit is saved locally", result.stderr)
        self.assertEqual(self.network_commands(), [])
        (self.bin / "gitleaks").unlink()
        result = self.run_hook()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.network_commands(), [])

    def test_full_history_is_checked_despite_tracking_ref(self):
        self.commit("Sensitive fixture", "credential-fixture\n")
        contaminated = self.git("rev-parse", "HEAD")
        self.commit("Clean current file", "ordinary configuration\n")
        self.git("update-ref", "refs/remotes/origin/main", contaminated)
        self.git("config", "dotfiles.autoSync", "true")
        self.run_hook()
        self.assertEqual(self.network_commands(), [])

    def test_no_upstream_local_upstream_invalid_upstream_and_detached_are_safe(self):
        self.git("config", "dotfiles.autoSync", "true")
        for remote, ref in [(None, "refs/heads/main"), (".", "refs/heads/main"),
                            ("origin", "refs/tags/release"), ("origin", "refs/heads/bad name")]:
            with self.subTest(remote=remote, ref=ref):
                self.git("config", "--unset-all", "branch.main.remote", check=False)
                if remote is not None:
                    self.git("config", "branch.main.remote", remote)
                self.git("config", "branch.main.merge", ref)
                self.assertEqual(self.run_hook().returncode, 0)
                self.assertEqual(self.network_commands(), [])
        self.git("checkout", "--detach", "-q")
        self.assertEqual(self.run_hook().returncode, 0)
        self.assertEqual(self.network_commands(), [])

    def test_push_failure_keeps_commit_and_suppresses_transport_details(self):
        self.git("config", "dotfiles.autoSync", "true")
        self.env["SYNC_TEST_REJECT_PUSH"] = "1"
        before = self.git("rev-parse", "HEAD")
        result = self.run_hook()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.git("rev-parse", "HEAD"), before)
        self.assertIn("Auto-push failed", result.stderr)
        self.assertIn("commit is saved locally", result.stderr)
        self.assertNotIn("private-transport-output", result.stdout + result.stderr)
        self.assertEqual(len(self.network_commands()), 1)

    def test_multiple_push_destinations_do_not_connect(self):
        self.git("config", "dotfiles.autoSync", "true")
        self.git("config", "--add", "remote.origin.pushurl", str(self.remote))
        self.git("config", "--add", "remote.origin.pushurl", str(self.root / "another-destination.git"))
        result = self.run_hook()
        self.assertEqual(result.returncode, 0)
        self.assertIn("exactly one push destination", result.stderr)
        self.assertEqual(self.network_commands(), [])
        self.assertNotIn(str(self.remote), result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
