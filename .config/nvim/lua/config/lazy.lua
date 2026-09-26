local machine = require("config.machine")
local settings = machine.get()

-- Disable unused built-in plugins
vim.g.loaded_netrw = 1
vim.g.loaded_netrwPlugin = 1
local disabled_built_ins = {
  "gzip", "zip", "zipPlugin", "tar", "tarPlugin",
  "getscript", "getscriptPlugin", "vimball", "vimballPlugin",
  "2html_plugin", "matchit", "matchparen",
  "loaderPlugin", "tutor_mode_plugin",
}
for _, plugin in pairs(disabled_built_ins) do
  vim.g["loaded_" .. plugin] = 1
end

-- Leader key must be set before lazy.setup
vim.g.mapleader = ","

-- Bootstrap lazy.nvim
local lazypath = vim.fn.stdpath("data") .. "/lazy/lazy.nvim"
if not vim.uv.fs_stat(lazypath) then
  if not settings.features.bootstrap or not machine.executable("git") then
    machine.warn("lazy.nvim is missing; install it or enable bootstrap with Git available")
    return
  end
  local result = vim.fn.system({
    machine.tool("git"),
    "clone",
    "--filter=blob:none",
    "https://github.com/folke/lazy.nvim.git",
    "--branch=stable",
    lazypath,
  })
  if vim.v.shell_error ~= 0 then
    error("Could not install lazy.nvim: " .. result)
  end
end
vim.opt.rtp:prepend(lazypath)

-- Auto-discover all plugin specs in lua/plugins/ (including subdirectories)
require("lazy").setup({
  { import = "plugins" },
  { import = "plugins.lang" },
}, {
  rocks = { enabled = false },
  install = { missing = settings.features.bootstrap },
  checker = { enabled = false },
  change_detection = { notify = false },
})
