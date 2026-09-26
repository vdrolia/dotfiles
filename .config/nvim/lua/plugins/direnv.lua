return {
  "direnv/direnv.vim",
  lazy = false,
  cond = function()
    local machine = require("config.machine")
    return machine.get().features.direnv and machine.executable("direnv")
  end,
  init = function() vim.g.direnv_cmd = require("config.machine").tool("direnv") end,
}
