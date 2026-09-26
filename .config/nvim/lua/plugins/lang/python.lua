return {
  -- Virtual environment selector
  {
    "linux-cultist/venv-selector.nvim",
    cond = function()
      local machine = require("config.machine")
      return machine.get().features.python and (machine.executable("fd") or vim.fn.executable("fdfind") == 1)
    end,
    dependencies = { "neovim/nvim-lspconfig" },
    ft = "python",
    keys = {
      { "<leader>cv", "<cmd>VenvSelect<cr>", desc = "Select Venv", ft = "python" },
    },
    opts = function()
      local machine = require("config.machine")
      return { options = { fd_binary_name = machine.executable("fd") and machine.tool("fd") or "fdfind" } }
    end,
  },

  -- Debug adapter
  {
    "mfussenegger/nvim-dap",
    cond = function() return require("config.machine").get().features.python end,
    dependencies = {
      "mfussenegger/nvim-dap-python",
      "rcarriga/nvim-dap-ui",
      "nvim-neotest/nvim-nio",
    },
    ft = "python",
    keys = {
      { "<leader>db", function() require("dap").toggle_breakpoint() end, desc = "DAP: Toggle Breakpoint" },
      { "<leader>dc", function() require("dap").continue() end, desc = "DAP: Continue" },
      { "<leader>do", function() require("dap").step_over() end, desc = "DAP: Step Over" },
      { "<leader>di", function() require("dap").step_into() end, desc = "DAP: Step Into" },
      { "<leader>dO", function() require("dap").step_out() end, desc = "DAP: Step Out" },
      { "<leader>dr", function() require("dap").repl.open() end, desc = "DAP: REPL" },
      { "<leader>du", function() require("dapui").toggle() end, desc = "DAP: Toggle UI" },
    },
    config = function()
      require("config.python").setup_dap()
      local opts = {}
      if not require("config.machine").get().icons.enabled then
        opts = { icons = { expanded = "-", collapsed = "+", current_frame = ">" },
          controls = { icons = { pause = "||", play = ">", step_into = "v", step_over = ">",
            step_out = "^", step_back = "<", run_last = ">", terminate = "X", disconnect = "X" } } }
      end
      require("dapui").setup(opts)
    end,
  },

  -- Test runner
  {
    "nvim-neotest/neotest",
    cond = function() return require("config.machine").get().features.python end,
    dependencies = {
      "nvim-neotest/neotest-python",
      "nvim-neotest/nvim-nio",
    },
    ft = "python",
    keys = {
      { "<leader>nn", function() require("neotest").run.run() end, desc = "Test: Nearest" },
      { "<leader>nf", function() require("neotest").run.run(vim.fn.expand("%")) end, desc = "Test: File" },
      { "<leader>no", function() require("neotest").output_panel.toggle() end, desc = "Test: Output" },
      { "<leader>ns", function() require("neotest").summary.toggle() end, desc = "Test: Summary" },
    },
    config = function()
      require("neotest").setup({
        adapters = {
          require("neotest-python")({
            python = require("config.machine").get().tools.python
              and function(root) return require("config.python").project(root) end or nil,
            dap = { justMyCode = false },
          }),
        },
      })
    end,
  },
}
