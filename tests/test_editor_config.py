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
    def test_existing_vimrc_owns_its_implicit_private_overlay(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            conventional = temp / "conventional.vim"
            conventional.write_text("let g:overlay_loads = get(g:, 'overlay_loads', 0) + 1\n")
            shared = temp / "shared.vim"
            # Redirect only the conventional filename in a fixture; never
            # create home files or override HOME for an editor subprocess.
            shared.write_text((REPO / ".vimrc").read_text().replace("'~/.vimrc.local'", repr(str(conventional))))
            wrapper = temp / "existing.vim"
            wrapper.write_text(
                "let g:dotfiles_coexist = 1\nlet g:dotfiles_enable_plugins = 0\nlet g:dotfiles_fzf_path = ''\n"
                "execute 'source ' . fnameescape(" + repr(str(shared)) + ")\n"
                "let g:shared_overlay_loads = get(g:, 'overlay_loads', 0)\n"
                "execute 'source ' . fnameescape(" + repr(str(conventional)) + ")\n"
            )
            output = temp / "result.json"
            script = temp / "verify.vim"
            script.write_text(
                "call writefile([json_encode({'shared': g:shared_overlay_loads, 'final': g:overlay_loads})], "
                + repr(str(output)) + ")\nqa!\n"
            )
            env = dict(os.environ, XDG_CACHE_HOME=str(temp / "cache"))
            env.pop("DOTFILES_VIM_LOCAL", None)
            result = subprocess.run([shutil.which("vim"), "-N", "-n", "-i", "NONE", "-es",
                                     "--cmd", "set runtimepath=$VIMRUNTIME",
                                     "-u", str(wrapper), "-S", str(script)],
                                    env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(output.read_text()), {"shared": 0, "final": 1})

    @unittest.skipUnless(shutil.which("vim"), "Vim is unavailable")
    def test_existing_vimrc_owns_plugins_and_overrides_with_once_only_shared_source(self):
        for explicit in [False, True]:
            with self.subTest(explicit_plugins=explicit), tempfile.TemporaryDirectory() as directory:
                temp = Path(directory)
                checkout = temp / "another checkout"
                checkout.mkdir()
                shared = checkout / ".vimrc"
                shutil.copyfile(REPO / ".vimrc", shared)
                runtime = temp / "runtime"
                (runtime / "autoload").mkdir(parents=True)
                (runtime / "autoload/plug.vim").write_text(
                    "function! plug#begin(...)\n"
                    " let g:plugin_bootstraps = get(g:, 'plugin_bootstraps', 0) + 1\n"
                    " command! -nargs=+ Plug let g:plugin_declared = 1\n"
                    "endfunction\nfunction! plug#end()\nendfunction\n"
                )
                (runtime / "autoload/glaive.vim").write_text(
                    "function! glaive#Install()\n"
                    " let g:glaive_bootstraps = get(g:, 'glaive_bootstraps', 0) + 1\nendfunction\n"
                )
                local = temp / "private.vim"
                local.write_text(
                    "let g:dotfiles_fzf_path = ''\n"
                    "let g:dotfiles_backupdir = " + repr(str(temp / "backup")) + "\n"
                    "let g:dotfiles_swapdir = " + repr(str(temp / "swap")) + "\n"
                    + ("let g:dotfiles_enable_plugins = 1\n" if explicit else "")
                )
                wrapper = temp / "existing.vim"
                wrapper.write_text(
                    "let g:dotfiles_coexist = 1\n"
                    "execute 'source ' . fnameescape(" + repr(str(shared)) + ")\n"
                    "unlet g:dotfiles_coexist\n"
                    "let g:shared_bootstraps = get(g:, 'plugin_bootstraps', 0)\n"
                    "call plug#begin()\ncall plug#end()\n"
                    "set numberwidth=9\nlet mapleader = ';'\n"
                    "nnoremap <F3> :echo 'existing mapping'<CR>\n"
                )
                output = temp / "result.json"
                script = temp / "verify.vim"
                script.write_text(
                    "execute 'source ' . fnameescape(" + repr(str(shared)) + ")\n"
                    "call writefile([json_encode({'shared': g:shared_bootstraps, "
                    "'plugins': g:plugin_bootstraps, 'glaive': get(g:, 'glaive_bootstraps', 0), "
                    "'numberwidth': &numberwidth, 'leader': mapleader, 'mapping': maparg('<F3>', 'n'), "
                    "'autocmds': execute('autocmd FileType yaml')})], " + repr(str(output)) + ")\nqa!\n"
                )
                result = subprocess.run([shutil.which("vim"), "-N", "-n", "-i", "NONE", "-es",
                                         "--cmd", "set runtimepath=" + str(runtime) + ",$VIMRUNTIME",
                                         "-u", str(wrapper), "-S", str(script)],
                                        env=dict(os.environ, DOTFILES_VIM_LOCAL=str(local)),
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                state = json.loads(output.read_text())
                self.assertEqual(state["shared"], int(explicit))
                self.assertEqual(state["plugins"], int(explicit) + 1)
                self.assertEqual(state["glaive"], int(explicit))
                self.assertEqual(state["numberwidth"], 9)
                self.assertEqual(state["leader"], ";")
                self.assertIn("existing mapping", state["mapping"])
                self.assertEqual(state["autocmds"].count("setlocal ts=2 sts=2 sw=2 expandtab"), 1)

    @unittest.skipUnless(shutil.which("vim"), "Vim is unavailable")
    def test_backup_and_swap_paths_with_spaces_and_commas(self):
        for leaf in ["with spaces", "with,commas", "with spaces,and commas"]:
            with self.subTest(leaf=leaf), tempfile.TemporaryDirectory() as directory:
                temp = Path(directory)
                backup = temp / ("backup-" + leaf)
                swap = temp / ("swap-" + leaf)
                local = temp / "local.vim"
                local.write_text(
                    "let g:dotfiles_enable_plugins = 0\n"
                    "let g:dotfiles_fzf_path = ''\n"
                    "let g:dotfiles_backupdir = " + repr(str(backup)) + "\n"
                    "let g:dotfiles_swapdir = " + repr(str(swap)) + "\n"
                )
                source = temp / "sample.txt"
                source.write_text("original content\n")
                output = temp / "result.json"
                script = temp / "verify.vim"
                script.write_text(
                    # Vim normally skips backups for temporary input files.
                    "set backupskip= updatecount=1 swapfile\n"
                    "execute 'edit ' . fnameescape(" + repr(str(source)) + ")\n"
                    "let v:errmsg = ''\n"
                    "call setline(1, 'saved content')\nwrite\n"
                    "call setline(1, 'unsaved content')\npreserve\n"
                    "let s:swap = swapname('%')\n"
                    "call writefile([json_encode({'error': v:errmsg, 'swap': s:swap, "
                    "'swap_exists': filereadable(s:swap)})], " + repr(str(output)) + ")\nqa!\n"
                )
                result = subprocess.run([shutil.which("vim"), "-N", "-i", "NONE", "-es",
                                         "--cmd", "set runtimepath=$VIMRUNTIME",
                                         "-u", str(REPO / ".vimrc"), "-S", str(script)],
                                        env=dict(os.environ, DOTFILES_VIM_LOCAL=str(local)),
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                state = json.loads(output.read_text())
                self.assertEqual(state["error"], "")
                self.assertEqual(source.read_text(), "saved content\n")
                backups = list(backup.iterdir())
                self.assertEqual(len(backups), 1)
                self.assertEqual(backups[0].read_text(), "original content\n")
                self.assertEqual(state["swap_exists"], 1)
                self.assertEqual(Path(state["swap"]).parent.resolve(), swap.resolve())

    @unittest.skipUnless(shutil.which("vim"), "Vim is unavailable")
    def test_insert_format_mapping_invokes_command_and_resumes_typing(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            local = temp / "local.vim"
            local.write_text(
                "let g:dotfiles_enable_plugins = 0\n"
                "let g:dotfiles_fzf_path = ''\n"
                "let g:dotfiles_backupdir = " + repr(str(temp / "backup")) + "\n"
                "let g:dotfiles_swapdir = " + repr(str(temp / "swap")) + "\n"
            )
            output = temp / "result.json"
            script = temp / "verify.vim"
            script.write_text(
                "let g:format_called = 0\n"
                "command! FormatCode let g:format_called += 1\n"
                "call feedkeys(\"iabc\\<C-F>def\\<Esc>\", 'xt')\n"
                "call writefile([json_encode({'calls': g:format_called, 'lines': getline(1, '$')})], "
                + repr(str(output)) + ")\nqa!\n"
            )
            result = subprocess.run([shutil.which("vim"), "-N", "-n", "-i", "NONE", "-es",
                                     "--cmd", "set runtimepath=$VIMRUNTIME",
                                     "-u", str(REPO / ".vimrc"), "-S", str(script)],
                                    env=dict(os.environ, DOTFILES_VIM_LOCAL=str(local)),
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            state = json.loads(output.read_text())
            self.assertEqual(state["calls"], 1)
            self.assertEqual(state["lines"], ["abcdef"])

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
    def test_existing_tmux_settings_win_and_implicit_overlay_is_not_loaded(self):
        for explicit in [False, True]:
            with self.subTest(explicit_overlay=explicit), tempfile.TemporaryDirectory() as directory:
                temp = Path(directory)
                checkout = temp / "another checkout"
                checkout.mkdir()
                conventional = temp / "conventional.conf"
                conventional.write_text("set -g @private_overlay_loaded 1\n")
                shared = checkout / ".tmux.conf"
                shared.write_text((REPO / ".tmux.conf").read_text().replace("~/.tmux.conf.local", str(conventional)))
                wrapper = temp / "existing.conf"
                wrapper.write_text(
                    "set -g @dotfiles_coexist 1\n"
                    'source-file "' + str(shared) + '"\n'
                    "set -gu @dotfiles_coexist\nset -g history-limit 7654\nset -g prefix C-a\n"
                    'bind-key -T copy-mode-vi y display-message "existing-binding"\n'
                )
                fake_bin = temp / "bin"
                fake_bin.mkdir()
                (fake_bin / "uname").write_text("#!/bin/sh\nprintf '%s\\n' Linux\n")
                (fake_bin / "uname").chmod(0o700)
                socket = "dotfiles-test-" + uuid.uuid4().hex
                tmux = shutil.which("tmux")
                env = dict(os.environ, DISPLAY="", WAYLAND_DISPLAY="",
                           PATH=str(fake_bin) + os.pathsep + os.environ.get("PATH", os.defpath))
                env.pop("TMUX", None)
                env.pop("DOTFILES_TMUX_LOCAL", None)
                if explicit:
                    env["DOTFILES_TMUX_LOCAL"] = str(conventional)
                try:
                    result = subprocess.run([tmux, "-L", socket, "-f", str(wrapper),
                                             "new-session", "-d", "-s", "check", "/bin/sleep 30"],
                                            env=env, capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    history = subprocess.check_output([tmux, "-L", socket, "show-option", "-gv", "history-limit"], env=env)
                    prefix = subprocess.check_output([tmux, "-L", socket, "show-option", "-gv", "prefix"], env=env)
                    self.assertEqual(history.decode().strip(), "7654")
                    self.assertEqual(prefix.decode().strip(), "C-a")
                    binding = subprocess.check_output([tmux, "-L", socket, "list-keys", "-T", "copy-mode-vi", "y"], env=env).decode()
                    self.assertIn("existing-binding", binding)
                    overlay = subprocess.run([tmux, "-L", socket, "show-option", "-gv", "@private_overlay_loaded"],
                                             env=env, capture_output=True, text=True)
                    self.assertEqual(overlay.returncode == 0, explicit)
                finally:
                    subprocess.run([tmux, "-L", socket, "kill-server"], env=env, capture_output=True)

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
