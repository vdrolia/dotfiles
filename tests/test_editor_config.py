"""Exercise editors only with temporary local settings and isolated servers."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import uuid

REPO = Path(__file__).resolve().parents[1]


class EditorConfigTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("vim"), "Vim is unavailable")
    def test_unnamed_startup_uses_native_filetype_detection(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            runtime = temp / "runtime"
            (runtime / "ftdetect").mkdir(parents=True)
            # Reproduce the installed legacy Polyglot hook: <afile>:e errors on
            # an unnamed buffer in modern Vim. Its supported opt-out keeps the
            # language packs and delegates filetype detection to Vim itself.
            (runtime / "ftdetect/polyglot.vim").write_text(
                "if index(get(g:, 'polyglot_disabled', []), 'ftdetect') < 0\n"
                " autocmd BufWinEnter * if &ft == '' && expand('<afile>:e') == '' | let g:legacy_detection = 1 | endif\n"
                "endif\n"
            )
            local = temp / "local.vim"
            local.write_text(
                "let g:dotfiles_enable_plugins = 0\n"
                "let g:dotfiles_fzf_path = " + repr(str(temp / "missing-fzf")) + "\n"
                "let g:dotfiles_backupdir = " + repr(str(temp / "backup")) + "\n"
                "let g:dotfiles_swapdir = " + repr(str(temp / "swap")) + "\n"
            )
            named = temp / "sample.py"
            named.write_text("print('sample')\n")
            output = temp / "result.json"
            script = temp / "verify.vim"
            script.write_text(
                "let s:startup_error = v:errmsg\n"
                "execute 'edit ' . fnameescape(" + repr(str(named)) + ")\n"
                "let s:filetype = &filetype\n"
                "enew\n"
                "call writefile([json_encode({'startup_error': s:startup_error, "
                "'final_error': v:errmsg, 'filetype': s:filetype})], " + repr(str(output)) + ")\nqa!\n"
            )
            result = subprocess.run([shutil.which("vim"), "-N", "-n", "-i", "NONE", "-es",
                                     "-V1" + str(temp / "startup.log"),
                                     "--cmd", "set runtimepath=" + str(runtime) + ",$VIMRUNTIME",
                                     "-u", str(REPO / ".vimrc"), "-S", str(script)],
                                    env=dict(os.environ, DOTFILES_VIM_LOCAL=str(local)),
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            state = json.loads(output.read_text())
            self.assertEqual(state["startup_error"], "")
            self.assertEqual(state["final_error"], "")
            self.assertEqual(state["filetype"], "python")

    @unittest.skipUnless(shutil.which("vim"), "Vim is unavailable")
    def test_vim_without_plugins_and_private_options_before_bootstrap(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            local = temp / "local.vim"
            output = temp / "result.json"
            local.write_text(
                "let g:dotfiles_enable_plugins = 1\n"
                "let g:dotfiles_fzf_path = " + repr(str(temp / "missing-fzf")) + "\n"
                "let g:dotfiles_backupdir = " + repr(str(temp / "backup")) + "\n"
                "let g:dotfiles_swapdir = " + repr(str(temp / "swap")) + "\n"
                "let g:dotfiles_shell = '/bin/sh'\n"
                "let g:dotfiles_clipboard = ''\n"
                "function! DotfilesVimLocal()\n set numberwidth=7\nendfunction\n"
            )
            script = temp / "verify.vim"
            script.write_text(
                "call writefile([json_encode({'shell': &shell, 'backup': &backupdir, "
                "'swap': &directory, 'numberwidth': &numberwidth})], " + repr(str(output)) + ")\nqa!\n"
            )
            result = subprocess.run([shutil.which("vim"), "-N", "-n", "-i", "NONE", "-es",
                                     "--cmd", "set runtimepath=$VIMRUNTIME",
                                     "-u", str(REPO / ".vimrc"), "-S", str(script)],
                                    env=dict(os.environ, DOTFILES_VIM_LOCAL=str(local)),
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            state = json.loads(output.read_text())
            self.assertEqual(state["shell"], "/bin/sh")
            self.assertEqual(state["numberwidth"], 7)
            self.assertIn(str(temp), state["backup"])
            self.assertTrue((temp / "backup").is_dir())

    @unittest.skipUnless(shutil.which("tmux"), "tmux is unavailable")
    def test_tmux_headless_copy_and_private_override(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            local = temp / "local.conf"
            local.write_text("set -g history-limit 3210\nset -g default-shell /bin/sh\n")
            fake_bin = temp / "bin"
            fake_bin.mkdir()
            uname = fake_bin / "uname"
            uname.write_text("#!/bin/sh\nprintf '%s\\n' Linux\n")
            uname.chmod(0o700)
            socket = "dotfiles-test-" + uuid.uuid4().hex
            tmux = shutil.which("tmux")
            env = dict(os.environ, DOTFILES_TMUX_LOCAL=str(local), DISPLAY="", WAYLAND_DISPLAY="",
                       PATH=str(fake_bin) + os.pathsep + os.environ.get("PATH", os.defpath))
            env.pop("TMUX", None)
            try:
                result = subprocess.run([tmux, "-L", socket, "-f", str(REPO / ".tmux.conf"),
                                         "new-session", "-d", "-s", "check", "/bin/sleep 30"],
                                        env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                value = subprocess.check_output([tmux, "-L", socket, "show-option", "-gv", "history-limit"], env=env)
                self.assertEqual(value.decode().strip(), "3210")
                binding = subprocess.check_output([tmux, "-L", socket, "list-keys", "-T", "copy-mode-vi", "y"], env=env).decode()
                self.assertIn("copy-selection-and-cancel", binding)
            finally:
                subprocess.run([tmux, "-L", socket, "kill-server"], env=env, capture_output=True)


if __name__ == "__main__":
    unittest.main()
