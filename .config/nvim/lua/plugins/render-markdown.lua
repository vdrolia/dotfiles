return {
  "MeanderingProgrammer/render-markdown.nvim",
  ft = { "markdown", "codecompanion" },
  dependencies = {
    "nvim-treesitter/nvim-treesitter",
    "nvim-tree/nvim-web-devicons",
  },
  keys = {
    { "<leader>mt", "<cmd>RenderMarkdown buf_toggle<cr>", desc = "Toggle render" },
    { "<leader>me", "<cmd>RenderMarkdown expand<cr>", desc = "Expand anti-conceal" },
    { "<leader>mc", "<cmd>RenderMarkdown contract<cr>", desc = "Contract anti-conceal" },
  },
  opts = function()
    local icons = require("config.machine").get().icons.enabled
    return {
    sign = { enabled = icons },
    link = { enabled = icons },
    preset = "obsidian",
    heading = {
      icons = not icons and { "# ", "## ", "### ", "#### ", "##### ", "###### " } or nil,
      width = "block",
      min_width = 40,
      border = true,
      border_virtual = true,
    },
    code = {
      width = "block",
      min_width = 45,
      language_pad = 2,
      left_pad = 2,
      right_pad = 2,
    },
    checkbox = {
      unchecked = { icon = "  " },
      checked = { icon = "  " },
      custom = {
        todo = { raw = "[-]", rendered = icons and " 󰥔 " or " [-] ", highlight = "RenderMarkdownTodo" },
      },
    },
    bullet = {
      icons = icons and { "●", "○", "◆", "◇" } or { "-" },
    },
    pipe_table = {
      preset = "round",
    },
    }
  end,
}
