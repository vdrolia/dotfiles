return {
  -- Surround text objects
  {
    "kylechui/nvim-surround",
    version = "*",
    event = "VeryLazy",
    opts = {},
  },

  -- Auto-closing pairs
  {
    "windwp/nvim-autopairs",
    event = "InsertEnter",
    opts = {},
  },

  -- Flash navigation — jump to any visible position in 2-3 keystrokes
  {
    "folke/flash.nvim",
    event = "VeryLazy",
    keys = {
      { "s", mode = { "n", "x", "o" }, function() require("flash").jump() end, desc = "Flash" },
      { "S", mode = { "n", "x", "o" }, function() require("flash").treesitter() end, desc = "Flash Treesitter" },
    },
    opts = {},
  },

  -- Harpoon — quick file bookmarks
  {
    "ThePrimeagen/harpoon",
    branch = "harpoon2",
    lazy = true,
    dependencies = { "nvim-lua/plenary.nvim" },
    keys = {
      { "<leader>ha", function() require("harpoon"):list():append() end, desc = "Harpoon: Append" },
      { "<leader>hr", function() require("harpoon"):list():remove() end, desc = "Harpoon: Remove" },
      { "<leader>hx", function() require("harpoon"):list():clear() end, desc = "Harpoon: Clear" },
      { "<leader>hp", function() require("harpoon"):list():prev() end, desc = "Harpoon: Previous" },
      { "<leader>hn", function() require("harpoon"):list():next() end, desc = "Harpoon: Next" },
      {
        "<leader>hh",
        function()
          local harpoon = require("harpoon")
          local file_paths = {}
          for _, item in ipairs(harpoon:list().items) do
            table.insert(file_paths, item.value)
          end
          require("telescope.pickers").new({}, {
            prompt_title = "Harpoon",
            finder = require("telescope.finders").new_table({ results = file_paths }),
            previewer = require("telescope.config").values.file_previewer({}),
            sorter = require("telescope.config").values.generic_sorter({}),
          }):find()
        end,
        desc = "Harpoon: Window",
      },
    },
    config = function()
      require("harpoon"):setup()
    end,
  },

  -- TODO comments — highlight and search TODOs/FIXMEs
  {
    "folke/todo-comments.nvim",
    event = { "BufReadPost", "BufNewFile" },
    dependencies = { "nvim-lua/plenary.nvim" },
    opts = function()
      return { signs = require("config.machine").get().icons.enabled,
        search = { command = require("config.machine").tool("rg") } }
    end,
    keys = {
      { "<leader>ft", "<cmd>TodoTelescope<cr>", desc = "Find TODOs" },
    },
  },

  -- Project-wide search & replace with live preview
  {
    "MagicDuck/grug-far.nvim",
    cond = function() return require("config.machine").executable("rg") end,
    cmd = "GrugFar",
    keys = {
      { "<leader>sr", function() require('grug-far').open() end, desc = "Search & Replace" },
    },
    opts = function()
      return { engines = { ripgrep = { path = require("config.machine").tool("rg") } } }
    end,
  },

  -- Auto-detect file indentation
  {
    "NMAC427/guess-indent.nvim",
    event = "BufReadPre",
    opts = {},
  },
}
