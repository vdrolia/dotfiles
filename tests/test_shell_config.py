"""Exercise public shell setup with explicit private-config test fixtures."""

import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
ZSH = shutil.which("zsh")
ACK = shutil.which("ack")


@unittest.skipUnless(ZSH, "zsh is required")
class ShellConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="dotfiles shell test ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.local = self.root / "local"
        self.local.mkdir()
        # HOME keeps its real value. Every file that may be sourced is redirected.
        self.env = {
            "PATH": "/usr/bin:/bin",
            "HOME": os.environ["HOME"],
            "ZDOTDIR": str(self.root / "zsh-startup"),
            "DOTFILES_LOCAL_DIR": str(self.local),
            "DOTFILES_ZSH_LOCAL": str(self.root / "late.zsh"),
            "DOTFILES_BREW_PREFIX": "",
            "ZSH": str(self.root / "oh-my-zsh"),
            "ZSH_CUSTOM": str(self.root / "custom"),
            "ASDF_DIR": str(self.root / "legacy"),
            "ASDF_DATA_DIR": str(self.root / "asdf-data"),
            "BUN_INSTALL": str(self.root / "bun"),
            "HISTFILE": str(self.root / "history"),
            "LC_ALL": "C",
        }
        self.early("DOTFILES_USER_PATHS=()\n")

    def early(self, content):
        (self.local / "env.zsh").write_text("DOTFILES_USER_PATHS=()\n" + content)

    def file(self, relative, content="", executable=False):
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        if executable:
            target.chmod(0o700)
        return target

    def run_zsh(self, body, *, setup=True):
        source = REPO / (".zshrc" if setup else ".zshrc-functions")
        return subprocess.run(
            [ZSH, "-dfc", f"source {shlex.quote(str(source))}\n{body}"],
            cwd=self.root,
            env=self.env,
            text=True,
            capture_output=True,
            timeout=10,
        )

    def assert_success(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")

    def test_missing_optional_dependencies_and_overlays_are_quiet(self):
        result = self.run_zsh("print -r -- $?:${+functions[getBranch]}:${+functions[asdf]}")
        self.assert_success(result)
        self.assertEqual(result.stdout, "0:1:0\n")

    def test_early_plugin_settings_and_last_function_override(self):
        self.file("oh-my-zsh/plugins/git/git.plugin.zsh")
        self.file(
            "oh-my-zsh/oh-my-zsh.sh",
            'print -r -- "boot:$ZSH_THEME:${(j:,:)plugins}"\n',
        )
        self.early("ZSH_THEME=local-theme\nDOTFILES_ZSH_PLUGINS=(git absent)\n")
        self.file("late.zsh", "getBranch() { print -r -- late-override; }\n")
        result = self.run_zsh("getBranch")
        self.assert_success(result)
        self.assertEqual(result.stdout, "boot:local-theme:git\nlate-override\n")

    def test_path_order_spaces_and_repeat_source_deduplication(self):
        first = self.root / "first bin"
        second = self.root / "second bin"
        first.mkdir()
        second.mkdir()
        self.early(
            "DOTFILES_EXTRA_PATH=("
            + shlex.quote(str(first)) + " " + shlex.quote(str(second)) + ")\n"
        )
        result = self.run_zsh(
            f"source {shlex.quote(str(REPO / '.zshrc'))}\n"
            'print -rl -- "$path[1]" "$path[2]" "${#path}"'
        )
        self.assert_success(result)
        self.assertEqual(result.stdout.splitlines(), [str(first), str(second), "4"])

    def test_native_asdf_does_not_load_legacy_script(self):
        binary = self.file("bin/asdf", "#!/bin/sh\nprintf 'native:%s\\n' \"$1\"\n", True)
        legacy = self.file("legacy/asdf.sh", "print -u2 -- legacy-should-not-load\n")
        self.early(
            f"DOTFILES_EXTRA_PATH=({shlex.quote(str(binary.parent))})\n"
            f"DOTFILES_ASDF_SCRIPT={shlex.quote(str(legacy))}\n"
        )
        result = self.run_zsh("asdf version")
        self.assert_success(result)
        self.assertEqual(result.stdout, "native:version\n")

    def test_legacy_asdf_is_lazy_and_initializes_once(self):
        legacy = self.file(
            "legacy/asdf.sh",
            "print -r -- loading-legacy\nasdf() { print -r -- legacy:$1; }\n",
        )
        self.early(f"DOTFILES_ASDF_SCRIPT={shlex.quote(str(legacy))}\n")
        result = self.run_zsh("print -r -- before\nasdf first\nasdf second")
        self.assert_success(result)
        self.assertEqual(result.stdout, "before\nloading-legacy\nlegacy:first\nlegacy:second\n")

    def test_bun_completion_respects_local_install_path(self):
        self.file("bun/_bun", "print -r -- local-bun\n")
        result = self.run_zsh("true")
        self.assert_success(result)
        self.assertEqual(result.stdout, "local-bun\n")

    def test_opaque_branch_does_not_call_jira(self):
        result = self.run_zsh(
            "jira() { print -u2 -- jira-must-not-run; return 1; }\n"
            "getBranch EXAMPLE-42\ngetBranch EXAMPLE-42",
            setup=False,
        )
        self.assert_success(result)
        names = result.stdout.splitlines()
        self.assertEqual(len(names), 2)
        self.assertNotEqual(names[0], names[1])
        for name in names:
            self.assertRegex(name, r"^change-[0-9a-f]{16}$")

    def test_ticket_branch_context_requires_opt_in(self):
        result = self.run_zsh(
            "DOTFILES_BRANCH_TICKET_CONTEXT=1\n"
            "findSummary() { print -r -- 'Example summary'; }\n"
            "getBranch EXAMPLE-42",
            setup=False,
        )
        self.assert_success(result)
        self.assertEqual(result.stdout, "EXAMPLE-42-example-summary\n")

    def test_ec2_lookup_returns_only_id_and_preserves_name_argument(self):
        result = self.run_zsh(
            "DOTFILES_EC2_NAME='example instance'\n"
            "aws() {\n"
            "  [[ $4 == 'Name=tag:Name,Values=example instance' ]] || return 9\n"
            "  print -r -- i-0123456789abcdef0\n"
            "}\ngetEC2IdByName",
            setup=False,
        )
        self.assert_success(result)
        self.assertEqual(result.stdout, "i-0123456789abcdef0\n")

    def test_ambiguous_ec2_lookup_never_starts_an_instance(self):
        result = self.run_zsh(
            "aws() {\n"
            "  if [[ $2 == describe-instances ]]; then\n"
            "    print -r -- 'i-11111111 i-22222222'\n"
            "  else\n"
            "    print -r -- unexpected-mutation\n"
            "  fi\n"
            "}\nstartEC2ByName example",
            setup=False,
        )
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("Expected exactly one EC2 instance", result.stderr)

    @unittest.skipUnless(ACK, "ack is required")
    def test_ack_reads_current_syntax_and_selects_js(self):
        self.file("example.jsx", "needle\n")
        self.file("example.class", "needle\n")
        result = subprocess.run(
            [ACK, "--noenv", "--ackrc=" + str(REPO / ".ackrc"), "--nocolor", "--nogroup", "--js", "needle", "."],
            cwd=self.root,
            env=self.env,
            text=True,
            capture_output=True,
            timeout=10,
        )
        self.assert_success(result)
        self.assertIn("example.jsx:1:needle", result.stdout)
        self.assertNotIn("example.class", result.stdout)


if __name__ == "__main__":
    unittest.main()
