return {
  "nvim-tree/nvim-tree.lua",
  version = "*",
  cmd = { "NvimTreeToggle", "NvimTreeFocus", "NvimTreeOpen" },
  dependencies = { "nvim-tree/nvim-web-devicons" },
  keys = {
    { "<leader>tt", function() require("nvim-tree.api").tree.toggle() end, desc = "Tree: Toggle" },
    { "<leader>tf", function() require("nvim-tree.api").tree.focus() end, desc = "Tree: Focus" },
    { "<leader>tr", function() require("nvim-tree.api").tree.refresh() end, desc = "Tree: Refresh" },
    { "<leader>tE", function() require("nvim-tree.api").tree.expand_all() end, desc = "Tree: Expand All" },
    { "<leader>tW", function() require("nvim-tree.api").tree.collapse_all() end, desc = "Tree: Collapse All" },
  },
  opts = {
    sort = { sorter = "case_sensitive" },
    view = {
      width = { min = "30%" },
      float = { enable = false },
    },
    renderer = {
      group_empty = true,
      icons = { show = {
        file = require("config.machine").get().icons.enabled,
        folder = require("config.machine").get().icons.enabled,
        folder_arrow = require("config.machine").get().icons.enabled,
        git = require("config.machine").get().icons.enabled,
      } },
    },
    filters = { dotfiles = true },
  },
}
