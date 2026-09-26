-- Keep the editor and the pinned plugin API baseline together.
if vim.fn.has("nvim-0.11.3") == 0 or vim.fn.has("nvim-0.12") == 1 then
  vim.notify("This configuration supports Neovim 0.11.3–0.11.x; update the plugin pins before changing major/minor versions", vim.log.levels.ERROR)
  return
end
require("config.machine").get()
require("config.machine").apply_path()
require("config.options")
require("config.lazy")
require("config.keymaps")
require("config.autocmds")
