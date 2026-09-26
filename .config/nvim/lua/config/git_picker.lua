local M = {}

-- Resolve on every invocation: Neovim may have changed directories since startup.
function M.changed_files(cwd)
  local machine = require("config.machine")
  if not machine.executable("git") then return nil, "Git is not available" end
  local function git(args)
    local cmd = { machine.tool("git") }
    vim.list_extend(cmd, args)
    local result = vim.system(cmd, { cwd = cwd, text = true }):wait()
    if result.code ~= 0 then return nil end
    return vim.trim(result.stdout or "")
  end
  local root = git({ "rev-parse", "--show-toplevel" })
  if not root or root == "" then return nil, "Current directory is not a Git repository" end
  local base = machine.get().tools.git_base_branch
  if type(base) == "function" then base = base(root) end
  if not base or base == "" then
    base = git({ "symbolic-ref", "--quiet", "refs/remotes/origin/HEAD" })
  end
  if not base or base == "" then
    return nil, "No origin/HEAD; set tools.git_base_branch for this repository"
  end
  -- --end-of-options prevents a configured ref from becoming a Git option.
  local base_id = git({ "rev-parse", "--verify", "--end-of-options", base .. "^{commit}" })
  if not base_id then return nil, "Configured Git base branch is not a commit" end
  local merge_base = git({ "merge-base", "HEAD", base_id })
  if not merge_base then return nil, "Git branches have no merge base" end
  local result = vim.system({ machine.tool("git"), "diff", "--name-only", "-z", merge_base, "--" },
    { cwd = root }):wait()
  if result.code ~= 0 then return nil, "Git diff failed" end
  return vim.split(result.stdout or "", "\0", { plain = true, trimempty = true }), root, merge_base
end

function M.conflicts(cwd)
  local machine = require("config.machine")
  if not machine.executable("git") then return nil, "Git is not available" end
  local git = machine.tool("git")
  local root_result = vim.system({ git, "rev-parse", "--show-toplevel" }, { cwd = cwd, text = true }):wait()
  if root_result.code ~= 0 then return nil, "Current directory is not a Git repository" end
  local root = vim.trim(root_result.stdout)
  local result = vim.system({ git, "diff", "--name-only", "--diff-filter=U", "-z", "--" }, { cwd = root }):wait()
  if result.code ~= 0 then return nil, "Git conflict listing failed" end
  return vim.split(result.stdout or "", "\0", { plain = true, trimempty = true }), root
end

function M.open(conflicts)
  local files, root, base = (conflicts and M.conflicts or M.changed_files)(vim.fn.getcwd())
  if not files then return require("config.machine").warn(root) end
  local previewer = require("telescope.previewers").new_buffer_previewer({
    define_preview = function(self, entry)
      local command = { require("config.machine").tool("git"), "diff", "--no-ext-diff", "--no-color" }
      if base then table.insert(command, base) end
      vim.list_extend(command, { "--", entry.value })
      local result = vim.system(command, { cwd = root, text = true }):wait()
      local content = result.code == 0 and result.stdout or "Git diff could not be displayed"
      vim.api.nvim_buf_set_lines(self.state.bufnr, 0, -1, false, vim.split(content or "", "\n", { plain = true }))
      vim.bo[self.state.bufnr].filetype = "diff"
    end,
  })
  require("telescope.pickers").new({}, {
    prompt_title = conflicts and "Git conflicts" or "Git changed files",
    cwd = root,
    finder = require("telescope.finders").new_table({ results = files }),
    previewer = previewer,
    sorter = require("telescope.config").values.generic_sorter({}),
  }):find()
end

return M
