local icons = require("config.machine").get().icons.enabled
-- Diagnostic configuration
vim.diagnostic.config({
  virtual_text = {
    prefix = icons and '●' or '!',
    spacing = 4,
    severity = { min = vim.diagnostic.severity.WARN },
  },
  signs = {
    text = {
      [vim.diagnostic.severity.ERROR] = icons and '●' or 'E',
      [vim.diagnostic.severity.WARN] = icons and '●' or 'W',
      [vim.diagnostic.severity.INFO] = icons and '●' or 'I',
      [vim.diagnostic.severity.HINT] = icons and '●' or 'H',
    },
  },
  float = {
    border = 'rounded',
    source = true,
  },
  severity_sort = true,
  update_in_insert = false,
  underline = true,
})

-- Soft-wrap for code and markdown
vim.api.nvim_create_autocmd("FileType", {
  pattern = {
    "markdown", "lua", "python", "go", "javascript", "typescript",
    "typescriptreact", "javascriptreact", "json", "yaml", "bash", "sh",
    "ruby", "java", "kotlin", "swift", "sql", "html", "css", "vim",
  },
  callback = function()
    vim.wo.wrap = true
    vim.wo.linebreak = true
  end,
})

-- Defer LSP log level to avoid loading vim.lsp at startup
vim.api.nvim_create_autocmd('LspAttach', {
  once = true,
  callback = function()
    vim.lsp.set_log_level("warn")
  end,
})
