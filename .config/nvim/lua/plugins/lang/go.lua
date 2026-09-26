return {
  "ray-x/go.nvim",
  version = "v0.11",
  commit = "41a18f0c05534c375bafec7ed05cdb409c4abcc6",
  pin = true,
  ft = { "go" },
  cond = function()
    local machine = require("config.machine")
    return machine.get().features.go and machine.executable("go")
  end,
  dependencies = { "neovim/nvim-lspconfig", "nvim-treesitter/nvim-treesitter" },
  opts = function()
    return {
      go = require("config.machine").tool("go"),
      lsp_cfg = false, -- config/lsp owns gopls, including settings and capabilities
      dap_debug = vim.fn.executable("dlv") == 1, -- Go debugging needs Delve on PATH
    }
  end,
}
