return {
  "folke/which-key.nvim",
  event = "VeryLazy",
  opts = {
    icons = { mappings = require("config.machine").get().icons.enabled },
    spec = {
      { "<leader>f", group = "Find" },
      { "<leader>c", group = "Code" },
      { "<leader>x", group = "Trouble" },
      { "<leader>h", group = "Harpoon" },
      { "<leader>t", group = "Tree" },
      { "<leader>g", group = "Git" },
      { "<leader>s", group = "Search" },
      { "<leader>d", group = "Debug" },
      { "<leader>n", group = "Neotest" },
    },
  },
}
