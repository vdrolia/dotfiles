return {
  "stevearc/conform.nvim",
  event = "BufWritePre",
  cmd = { "ConformInfo" },
  keys = {
    {
      "<C-f>",
      function()
        require("conform").format({ async = false, timeout_ms = 5000, lsp_format = "fallback" })
      end,
      mode = { "n", "x" },
      desc = "Format",
    },
  },
  opts = function()
    local tools = require("config.machine").get().tools
    local configured = tools.formatters
    local formatters = {}
    for name, command in pairs(configured) do
      -- Conform resolves commands at use time, after Mason has updated PATH.
      formatters[name] = { command = command }
    end
    return {
    formatters = formatters,
    formatters_by_ft = tools.formatters_by_ft,
    format_on_save = function(bufnr)
      local bufname = vim.api.nvim_buf_get_name(bufnr)
      if bufname:match("node_modules") then return end
      return { timeout_ms = 3000, lsp_format = "fallback" }
    end,
    }
  end,
}
