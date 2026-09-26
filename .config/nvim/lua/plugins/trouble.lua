return {
  "folke/trouble.nvim",
  cmd = "Trouble",
  dependencies = { "nvim-tree/nvim-web-devicons" },
  keys = {
    { "<leader>xx", function() require("trouble").toggle("diagnostics") end, desc = "Trouble: Toggle" },
    { "<leader>xw", function() require("trouble").toggle("diagnostics") end, desc = "Trouble: Workspace Diagnostics" },
    { "<leader>xd", function() require("trouble").toggle({ mode = "diagnostics", filter = { buf = 0 } }) end, desc = "Trouble: Document Diagnostics" },
    { "<leader>xq", function() require("trouble").toggle("qflist") end, desc = "Trouble: Quickfix" },
    { "<leader>xl", function() require("trouble").toggle("loclist") end, desc = "Trouble: Location List" },
    { "<leader>cr", function() require("trouble").toggle("lsp_references") end, desc = "LSP References" },
    { "<leader>gr", function() require("trouble").toggle("lsp_references") end, desc = "LSP References" },
  },
  opts = function()
    if require("config.machine").get().icons.enabled then return {} end
    return { icons = { folder_closed = "+", folder_open = "-",
      indent = { top = "| ", middle = "| ", last = "` ", ws = "  " } } }
  end,
}
