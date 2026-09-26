return {
  {
    "nvim-treesitter/nvim-treesitter",
    branch = "master", -- frozen API compatible with Neovim 0.11
    commit = "cf12346a3414fa1b06af75c79faebe7f76df080a",
    pin = true,
    lazy = false,
    enabled = function() return require("config.machine").get().features.treesitter end,
    build = function()
      local settings = require("config.machine").get()
      if settings.tools.c_compiler then
        require("nvim-treesitter.install").compilers = { settings.tools.c_compiler }
      end
      local parsers = require("config.parsers").installable(settings.parsers.ensure_installed)
      if #parsers > 0 then vim.cmd({ cmd = "TSUpdate", args = parsers }) end
    end,
    dependencies = {
      {
        "nvim-treesitter/nvim-treesitter-textobjects",
        branch = "master",
        commit = "5ca4aaa6efdcc59be46b95a3e876300cfead05ef",
        pin = true,
      },
    },
    config = function()
      local machine = require("config.machine")
      local settings = machine.get()
      local compiler = settings.tools.c_compiler
      if compiler then require("nvim-treesitter.install").compilers = { compiler } end
      local parsers = require("config.parsers").installable(settings.parsers.ensure_installed)
      require("nvim-treesitter.configs").setup({
        ensure_installed = parsers,
        auto_install = false, -- don't install unexpected languages while opening files
        highlight = { enable = true },
        textobjects = {
          select = {
            enable = true, lookahead = true,
            keymaps = {
              af = "@function.outer", ["if"] = "@function.inner",
              ac = "@class.outer", ic = "@class.inner",
              aa = "@parameter.outer", ia = "@parameter.inner",
            },
          },
          move = {
            enable = true, set_jumps = true,
            goto_next_start = { ["]m"] = "@function.outer", ["]a"] = "@parameter.outer" },
            goto_previous_start = { ["[m"] = "@function.outer", ["[a"] = "@parameter.outer" },
          },
        },
      })
    end,
  },
}
