"""Neovim checks with isolated XDG directories; never load live plugin data.

Run: python3 -m unittest discover -s tests -p test_nvim_config.py -v
Optional integration: set DOTFILES_NVIM_TEST_PLUGIN_ROOT to a separate, populated
lazy.nvim plugin directory. Never point it at your live Neovim data directory.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
NVIM = shutil.which("nvim")


@unittest.skipUnless(NVIM, "Neovim is not installed")
class NeovimConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="dotfiles-nvim-test-")
        self.root = Path(self.temp.name)
        self.config = self.root / "config" / "nvim"
        shutil.copytree(REPO / ".config" / "nvim", self.config)
        self.local = self.root / "private.lua"
        self.local.write_text("return {features={bootstrap=false,auto_install=false,native_fzf=false,direnv=false},clipboard={enabled=false},icons={enabled=false}}")
        self.env = os.environ.copy()
        for key, subdir in (("XDG_CONFIG_HOME", "config"), ("XDG_DATA_HOME", "data"),
                            ("XDG_STATE_HOME", "state"), ("XDG_CACHE_HOME", "cache")):
            self.env[key] = str(self.root / subdir)
        self.env.update(DOTFILES_NVIM_LOCAL=str(self.local), GIT_OPTIONAL_LOCKS="0",
                        GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
        for key in ("NVIM_APPNAME", "VIMINIT", "EXINIT", "MYVIMRC"):
            self.env.pop(key, None)
        for key in ("VIRTUAL_ENV", "CONDA_PREFIX"):
            self.env.pop(key, None)

    def tearDown(self):
        self.temp.cleanup()

    def lua(self, body, startup=False):
        script = self.root / "check.lua"
        script.write_text("local ok, err = xpcall(function()\n" + body + "\nend, debug.traceback)\n"
                          "if not ok then io.stderr:write(err .. '\\n'); vim.cmd('cquit 1') else vim.cmd('qa!') end\n")
        command = [NVIM, "--headless", "-n", "-i", "NONE", "-u",
                   str(self.config / "init.lua") if startup else "NONE"]
        if not startup:
            command += ["--cmd", "lua vim.opt.rtp:prepend(" + json.dumps(str(self.config)) + ")"]
        command += ["-c", "lua dofile(" + json.dumps(str(script)) + ")"]
        result = subprocess.run(command, env=self.env, cwd=self.root, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotRegex(result.stdout, r"Error detected while processing|Failed to run `config`|E5113:")
        return result.stdout

    def test_all_lua_parses(self):
        self.lua("for _, file in ipairs(vim.fn.globpath(vim.fn.stdpath('config'), '**/*.lua', false, true)) do assert(loadfile(file)) end")

    def test_private_precedence_and_portable_defaults(self):
        self.local.write_text("return {resource_limits={typescript_memory_mb=3072},icons={enabled=false}}")
        self.lua("""
local m = require('config.machine')
assert(m.local_path() == vim.env.DOTFILES_NVIM_LOCAL)
assert(m.get().resource_limits.typescript_memory_mb == 3072)
assert(m.get().resource_limits.eslint_memory_mb == 1024)
assert(m.get().icons.enabled == false)
assert(m.get().paths.backup == vim.fs.joinpath(vim.fn.stdpath('state'), 'backup'))
assert(m.get().shell.command == nil)
""")
        del self.env["DOTFILES_NVIM_LOCAL"]
        self.env["DOTFILES_LOCAL_DIR"] = str(self.root / "other-private")
        self.lua("assert(require('config.machine').local_path() == vim.fs.joinpath(vim.env.DOTFILES_LOCAL_DIR, 'nvim.lua'))")
        del self.env["DOTFILES_LOCAL_DIR"]
        self.lua("assert(require('config.machine').local_path() == vim.fs.joinpath(vim.env.XDG_CONFIG_HOME, 'dotfiles', 'nvim.lua'))")

    def test_invalid_private_file_fails_visibly(self):
        self.local.write_text("return 'invalid'")
        self.lua("local ok, err = pcall(require('config.machine').get); assert(not ok and err:match('must return a table'))")
        self.local.write_text("return {resource_limits={eslint_memory_mb='large'}}")
        self.lua("local ok, err = pcall(require('config.machine').get); assert(not ok and err:match('positive integer'))")

    def test_empty_install_and_formatter_lists_replace_defaults(self):
        self.local.write_text("return {servers={ensure_installed={}},parsers={ensure_installed={}},tools={ensure_installed={},formatters_by_ft={markdown={}}}}")
        self.lua("""
local settings = require('config.machine').get()
assert(#settings.servers.ensure_installed == 0)
assert(#settings.parsers.ensure_installed == 0)
assert(#settings.tools.ensure_installed == 0)
assert(#settings.tools.formatters_by_ft.markdown == 0)
assert(settings.tools.formatters_by_ft.lua[1] == 'stylua')
""")

    def test_node_limit_preserves_unrelated_options(self):
        self.lua("""
local m = require('config.machine')
assert(m.node_options(1024, '--trace-warnings --max_old_space_size=8000') == '--trace-warnings --max-old-space-size=1024')
assert(m.node_options(2048, '--max-old-space-size 4000 --enable-source-maps') == '--enable-source-maps --max-old-space-size=2048')
""")

    def test_invalid_shell_does_not_apply_incompatible_flags(self):
        self.local.write_text("return {shell={command='/does/not/exist',cmdflag='invalid-powershell-flags'},clipboard={enabled=false}}")
        self.lua("""
local shell, flags = vim.o.shell, vim.o.shellcmdflag
require('config.options')
assert(vim.o.shell == shell and vim.o.shellcmdflag == flags)
""")

    def test_grammar_parsers_skip_missing_cli_without_blocking_other_languages(self):
        self.local.write_text("return {features={auto_install=true}}")
        self.lua("""
local machine = require('config.machine')
local real_executable = vim.fn.executable
machine.has_compiler = function() return true end
vim.fn.executable = function(command)
  if command == 'tree-sitter' then return 0 end
  if command == 'curl' then return 1 end
  return real_executable(command)
end
local messages = {}
machine.warn = function(message) table.insert(messages, message) end
local available = require('config.parsers').installable({'lua', 'swift'}, {
  lua = {install_info={}}, swift = {install_info={requires_generate_from_grammar=true}},
})
assert(vim.deep_equal(available, {'lua'}))
assert(#messages == 1 and messages[1]:match('swift') and messages[1]:match('tree%-sitter CLI'))
vim.fn.executable = real_executable
""")

    def git(self, cwd, *args):
        return subprocess.check_output(["git", "-c", "user.name=Test User", "-c",
                                        "user.email=test@example.invalid", *args], cwd=cwd,
                                       env=self.env, stderr=subprocess.DEVNULL, text=True)

    def make_git_repo(self, name):
        root = self.root / name
        root.mkdir()
        self.git(root, "init", "-b", "main")
        (root / "normal.txt").write_text("initial\n")
        self.git(root, "add", ".")
        self.git(root, "commit", "-m", "Initial")
        return root

    def test_git_picker_real_repositories_and_shell_characters(self):
        first = self.make_git_repo("repo with spaces")
        self.git(first, "update-ref", "refs/remotes/origin/main", "HEAD")
        self.git(first, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
        strange = "literal;$(echo harmless).txt"
        (first / strange).write_text("changed\n")
        self.git(first, "add", ".")
        second = self.make_git_repo("second")
        self.lua("""
local picker = require('config.git_picker')
local files, root = picker.changed_files(%s)
assert(#files == 1 and files[1] == %s, vim.inspect(files))
local missing, err = picker.changed_files(%s)
assert(missing == nil and err:match('origin/HEAD'))
require('config.machine').get().tools.git_base_branch = 'main'
local empty = picker.changed_files(%s)
assert(#empty == 0)
require('config.machine').get().tools.git_base_branch = '--bad-option'
local invalid = picker.changed_files(%s)
assert(invalid == nil)
""" % tuple(json.dumps(str(value)) for value in (first, strange, second, second, second)))

    def test_debug_adapter_is_distinct_from_project_interpreter(self):
        project = self.root / "project-python"
        adapter = self.root / "adapter-python"
        for path in (project, adapter):
            path.write_text("#!/bin/sh\nexit 0\n")
            path.chmod(0o700)
        self.local.write_text("return {tools={python=" + json.dumps(str(project)) +
                              ",debugpy_python=" + json.dumps(str(adapter)) + "}}")
        self.lua("""
local python = require('config.python')
assert(python.project() ~= python.debugpy())
assert(python.project():match('project%-python$'))
assert(python.debugpy():match('adapter%-python$'))
require('config.machine').get().tools.debugpy_python = '/does/not/exist'
assert(python.debugpy() == nil)
""")

    def use_plugin_fixture(self):
        plugin_root = Path(os.environ["DOTFILES_NVIM_TEST_PLUGIN_ROOT"]).resolve()
        lazy = self.root / "data" / "nvim" / "lazy"
        lazy.parent.mkdir(parents=True)
        lazy.symlink_to(plugin_root, target_is_directory=True)

    @unittest.skipUnless(os.environ.get("DOTFILES_NVIM_TEST_PLUGIN_ROOT"), "Isolated plugin fixture not supplied")
    def test_pinned_eslint_save_regression(self):
        self.use_plugin_fixture()
        self.lua("""
local buffer = vim.api.nvim_create_buf(true, false)
vim.api.nvim_set_current_buf(buffer)
local requests, warnings = {}, {}
local client = {
  name = 'eslint',
  supports_method = function() return false end,
  request_sync = function(_, method, params, _, bufnr)
    table.insert(requests, {method=method, params=params, buffer=bufnr})
  end,
}
-- Register the real command from the pinned native Neovim LSP definition.
vim.lsp.config.eslint.on_attach(client, buffer)
assert(vim.fn.exists(':LspEslintFixAll') == 2)
local original_get_client = vim.lsp.get_client_by_id
vim.lsp.get_client_by_id = function() return client end
vim.api.nvim_exec_autocmds('LspAttach', {
  buffer=buffer, group='lsp-attach', data={client_id=12345},
})
vim.lsp.get_client_by_id = original_get_client
local original_notify = vim.notify
vim.notify = function(message) table.insert(warnings, message) end
vim.api.nvim_exec_autocmds('BufWritePre', {buffer=buffer})
vim.notify = original_notify
assert(#requests == 1, 'Save did not invoke ESLint: ' .. vim.inspect(warnings))
assert(requests[1].method == 'workspace/executeCommand')
assert(requests[1].params.command == 'eslint.applyAllFixes')
assert(requests[1].params.arguments[1].uri == vim.uri_from_bufnr(buffer))
assert(requests[1].buffer == buffer)
assert(#warnings == 0, vim.inspect(warnings))
""", startup=True)

    @unittest.skipUnless(os.environ.get("DOTFILES_NVIM_TEST_PLUGIN_ROOT"), "Isolated plugin fixture not supplied")
    def test_pinned_telescope_declaration_filter_regression(self):
        self.use_plugin_fixture()
        self.lua("""
require('lazy').load({plugins={'telescope.nvim'}})
local picker = require('telescope.pickers').new({}, {
  finder=require('telescope.finders').new_table({results={}}),
})
local retained = {}
picker.sorter.score = function(_, _, entry) table.insert(retained, entry.value) end
-- Exercise Telescope's result processor with the configured ignore patterns.
local process = picker:get_result_processor(picker._find_id, '', function() end)
for _, filename in ipairs({'find.ts', 'build.ts', 'types.d.ts', 'src/types.d.ts', 'types.d.ts.bak', 'index.ts'}) do
  process({value=filename, filename=filename})
end
assert(vim.deep_equal(retained, {'find.ts', 'build.ts', 'types.d.ts.bak', 'index.ts'}), vim.inspect(retained))
""", startup=True)

    @unittest.skipUnless(os.environ.get("DOTFILES_NVIM_TEST_PLUGIN_ROOT"), "Isolated plugin fixture not supplied")
    def test_pinned_plugins_start_and_load_representative_features(self):
        self.use_plugin_fixture()
        python = self.root / ".venv" / "bin" / "python"
        python.parent.mkdir(parents=True)
        python.write_text("#!/bin/sh\nexit 0\n")
        python.chmod(0o700)
        (python.parent.parent / "pyvenv.cfg").write_text("home = test\n")
        self.lua("""
vim.wait(300, function() return false end)
assert(require('lazy.core.config').plugins['nvim-treesitter']._.loaded)
assert(vim.lsp.config.eslint.cmd_env.NODE_OPTIONS:match('max%-old%-space%-size=1024'))
assert(vim.lsp.config.gopls.settings.gopls.completeUnimported)
for _, sample in ipairs({
  {'lua', 'sample.lua', 'local value = 1'},
  {'markdown', 'sample.md', '# Test fixture'},
  {'python', 'sample.py', 'value = 1'},
  {'typescript', 'sample.ts', 'const value: number = 1;'},
  {'go', 'sample.go', 'package main'},
}) do
  local path = vim.fs.joinpath(vim.fn.getcwd(), sample[2])
  vim.fn.writefile({sample[3]}, path)
  vim.cmd.edit(path)
  vim.bo.filetype = sample[1]
  vim.wait(150, function() return false end)
end
-- Let asynchronous executable discovery finish, including the missing-tsserver path.
vim.wait(3500, function() return false end)
require('lazy').load({plugins={'telescope.nvim', 'easypick.nvim', 'nvim-cmp', 'nvim-tree.lua', 'trouble.nvim', 'conform.nvim'}})
assert(vim.fn.exists(':GitChangedFiles') == 2)
assert(vim.fn.exists(':Easypick') == 2)
local picker = require('config.git_picker')
local original, calls = picker.open, {}
picker.open = function(conflicts) table.insert(calls, conflicts or false) end
vim.cmd('Easypick git_changed_files')
vim.cmd('Easypick git_conflicts')
vim.cmd('GitChangedFiles')
assert(#calls == 3 and not calls[1] and calls[2] and not calls[3])
picker.open = original
assert(type(require('dap').adapters.python) == 'function')
local python = vim.fn.exepath('nvim') -- executable fixture; no process is launched here
require('config.machine').get().tools.debugpy_python = python
local adapter
require('dap').adapters.python(function(value) adapter = value end, {request='launch'})
assert(adapter.command == python and adapter.args[2] == 'debugpy.adapter')
local enriched
adapter.enrich_config({request='launch'}, function(value) enriched = value end)
assert(enriched.pythonPath == vim.fs.joinpath(vim.fn.getcwd(), '.venv', 'bin', 'python'), vim.inspect(enriched))
assert(require('config.machine').get().paths.backup:find(vim.env.XDG_STATE_HOME, 1, true))
""", startup=True)


if __name__ == "__main__":
    unittest.main()
