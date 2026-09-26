-- Public defaults. Private overrides live outside the symlinked config tree.
local M = {}
local settings

local function defaults()
  return {
    shell = {}, -- command, cmdflag, quote, xquote, redir and pipe
    clipboard = { enabled = true, mode = "unnamed" },
    icons = { enabled = true },
    paths = {
      bin = {}, -- directories to prepend before plugins resolve external commands
      backup = vim.fs.joinpath(vim.fn.stdpath("state"), "backup"),
      mason = vim.fs.joinpath(vim.fn.stdpath("data"), "mason"),
    },
    tools = {
      git = "git", rg = "rg", fd = "fd", cmake = "cmake", direnv = "direnv",
      go = "go", gopls = "gopls",
      ensure_installed = { "shfmt", "stylua", "debugpy", "prettier", "typescript-language-server" },
      formatters = {}, -- e.g. shfmt = "/path/to/shfmt"
      formatters_by_ft = {
        sh = { "shfmt" }, bash = { "shfmt" }, lua = { "stylua" },
        python = { "ruff_format", "ruff_organize_imports" }, markdown = { "prettier" },
      },
      -- debugpy_python: interpreter containing debugpy, NOT the project venv
      -- python: optional function returning the current project interpreter
    },
    resource_limits = { typescript_memory_mb = 2048, eslint_memory_mb = 1024 },
    servers = {
      ensure_installed = { "lua_ls", "eslint", "bashls", "basedpyright", "ruff", "marksman", "gopls" },
      configs = {}, -- Neovim LSP options, including cmd/cmd_env when needed
    },
    parsers = {
      ensure_installed = {
        "bash", "awk", "c", "comment", "diff", "dockerfile", "markdown", "markdown_inline",
        "gitcommit", "gitignore", "git_config", "git_rebase", "go", "graphql", "http",
        "java", "jq", "json", "json5", "jsdoc", "proto", "python", "ruby", "sql",
        "swift", "kotlin", "vim", "vimdoc", "yaml", "typescript", "lua", "javascript", "query",
      },
    },
    features = {
      bootstrap = true, auto_install = true, native_fzf = true,
      direnv = true, treesitter = true, go = true, python = true,
    },
  }
end

function M.local_path()
  if vim.env.DOTFILES_NVIM_LOCAL and vim.env.DOTFILES_NVIM_LOCAL ~= "" then
    return vim.fn.expand(vim.env.DOTFILES_NVIM_LOCAL)
  end
  local root = vim.env.DOTFILES_LOCAL_DIR
  if not root or root == "" then
    root = vim.fs.joinpath(vim.fs.dirname(vim.fn.stdpath("config")), "dotfiles")
  end
  return vim.fs.joinpath(vim.fn.expand(root), "nvim.lua")
end

function M.get()
  if settings then return settings end
  local overrides = {}
  local path = M.local_path()
  if vim.fn.filereadable(path) == 1 then
    local ok, value = pcall(dofile, path)
    if not ok then error("Private Neovim configuration failed: " .. tostring(value)) end
    if type(value) ~= "table" then error("Private Neovim configuration must return a table") end
    overrides = value
  elseif vim.env.DOTFILES_NVIM_LOCAL and vim.env.DOTFILES_NVIM_LOCAL ~= "" then
    error("DOTFILES_NVIM_LOCAL does not name a readable file")
  end
  settings = vim.tbl_deep_extend("force", defaults(), overrides)
  -- Empty lists mean "none", not "merge the defaults back in".
  for _, field in ipairs({ { "servers", "ensure_installed" }, { "parsers", "ensure_installed" },
    { "tools", "ensure_installed" }, { "paths", "bin" } }) do
    local group, key = unpack(field)
    if overrides[group] and overrides[group][key] ~= nil then
      local value = overrides[group][key]
      if type(value) ~= "table" or not vim.islist(value) then error(group .. "." .. key .. " must be a list") end
      settings[group][key] = vim.deepcopy(value)
    end
  end
  if overrides.tools and overrides.tools.formatters_by_ft then
    for ft, list in pairs(overrides.tools.formatters_by_ft) do
      settings.tools.formatters_by_ft[ft] = vim.deepcopy(list)
    end
  end
  for key, value in pairs(settings.resource_limits) do
    if type(value) ~= "number" or value < 1 or value % 1 ~= 0 then
      error("resource_limits." .. key .. " must be a positive integer")
    end
  end
  return settings
end

function M.apply_path()
  local separator = vim.fn.has("win32") == 1 and ";" or ":"
  local prefixes = {}
  for _, path in ipairs(M.get().paths.bin) do
    table.insert(prefixes, vim.fn.expand(path))
  end
  if #prefixes > 0 then
    vim.env.PATH = table.concat(prefixes, separator) .. separator .. (vim.env.PATH or "")
  end
end

function M.tool(name)
  return M.get().tools[name] or name
end

function M.executable(name)
  local command = M.tool(name)
  return type(command) == "string" and vim.fn.executable(command) == 1
end

function M.has_compiler()
  local compiler = M.get().tools.c_compiler
  if compiler then return vim.fn.executable(compiler) == 1 end
  for _, command in ipairs({ "cc", "clang", "gcc", "cl" }) do
    if vim.fn.executable(command) == 1 then return true end
  end
  return false
end

function M.warn(message)
  vim.schedule(function() vim.notify(message, vim.log.levels.WARN) end)
end

-- Set only the child Node process's limit; preserve unrelated inherited options.
function M.node_options(limit, inherited)
  local value = inherited or vim.env.NODE_OPTIONS or ""
  value = value:gsub('["\']%-%-max[_-]old[_-]space[_-]size[= ]+%d+["\']', "")
  value = value:gsub("%-%-max[_-]old[_-]space[_-]size[= ]+%d+", "")
  value = vim.trim(value)
  return (value ~= "" and value .. " " or "") .. "--max-old-space-size=" .. tostring(limit)
end

return M
