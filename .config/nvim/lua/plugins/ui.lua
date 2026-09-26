return {
  -- Icons
  { "nvim-tree/nvim-web-devicons", lazy = true },

  -- UI improvements for inputs/selection
  { "stevearc/dressing.nvim", event = "VeryLazy" },

  -- Statusline
  {
    "nvim-lualine/lualine.nvim",
    event = "VeryLazy",
    dependencies = { "nvim-tree/nvim-web-devicons" },
    opts = {
      options = { theme = "onedark", icons_enabled = require("config.machine").get().icons.enabled },
      sections = {
        lualine_a = { 'mode' },
        lualine_b = { 'branch', 'diff', 'diagnostics' },
        lualine_c = { { 'filename', path = 1 } },
        lualine_x = { 'encoding', 'fileformat', 'filetype' },
        lualine_y = { 'progress' },
        lualine_z = { 'location' },
      },
    },
  },

  -- LSP progress notifications
  {
    "j-hui/fidget.nvim",
    event = "LspAttach",
    opts = {
      notification = { window = { winblend = 0 } },
    },
  },

  -- Indent guides
  {
    "lukas-reineke/indent-blankline.nvim",
    event = { "BufReadPost", "BufNewFile" },
    main = "ibl",
    opts = {
      indent = { char = require("config.machine").get().icons.enabled and "│" or "|" },
      scope = {
        enabled = true,
        include = {
          node_type = {
            -- Applies to all languages; fills gaps not covered by ibl's built-in defaults.
            -- Unknown node types are silently ignored, so this is safe to cast wide.
            ["*"] = {
              "if_statement", "if_expression",       -- missing from ecma/python defaults
              "try_statement",                        -- ecma only has catch_clause by default
              "finally_clause",                       -- not in ecma defaults
              "switch_statement", "switch_expression", -- not in ecma/python defaults
              "for_statement", "while_statement",     -- not in python defaults
              "do_statement",                         -- do-while in C/Java/Kotlin/Swift
            },
            -- Python: extra nodes ibl doesn't include by default
            python = { "except_clause", "with_statement" },
            -- Bash: grouping constructs and case
            bash = { "compound_statement", "case_statement" },
            -- Ruby: uses different names for try/rescue/ensure
            ruby = { "begin", "rescue", "ensure", "do_block", "block" },
          },
        },
      },
    },
  },
}
