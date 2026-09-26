return {
  "nvim-telescope/telescope.nvim",
  branch = "master",
  cmd = { "Telescope" },
  dependencies = {
    "nvim-lua/plenary.nvim",
    {
      "nvim-telescope/telescope-fzf-native.nvim",
      cond = function()
        local machine = require("config.machine")
        return machine.get().features.native_fzf and machine.executable("cmake") and machine.has_compiler()
      end,
      build = function(plugin)
        local machine = require("config.machine")
        local cmake = machine.tool("cmake")
        local configure = { cmake, "-S.", "-Bbuild", "-DCMAKE_BUILD_TYPE=Release" }
        local compiler = machine.get().tools.c_compiler
        if compiler then table.insert(configure, "-DCMAKE_C_COMPILER=" .. compiler) end
        for _, command in ipairs({ configure,
          { cmake, "--build", "build", "--config", "Release" },
          { cmake, "--install", "build", "--prefix", "build" },
        }) do
          local result = vim.system(command, { cwd = plugin.dir, text = true }):wait()
          if result.code ~= 0 then error("Native FZF build failed: " .. (result.stderr or result.stdout or "")) end
        end
      end,
    },
  },
  keys = {
    { "<C-p>", function() require('telescope.builtin').find_files() end, desc = "Find Files" },
    { "<leader>ff", function() require('telescope.builtin').find_files(require('telescope.themes').get_ivy()) end, desc = "Find File" },
    { "<leader>fg", function()
      local machine = require("config.machine")
      if not machine.executable("rg") then return machine.warn("Grep requires ripgrep") end
      require('telescope.builtin').live_grep(require('telescope.themes').get_ivy())
    end, desc = "Grep" },
    { "<leader>fb", function() require('telescope.builtin').buffers(require('telescope.themes').get_ivy()) end, desc = "Buffers" },
    { "<leader>fH", function() require('telescope.builtin').help_tags(require('telescope.themes').get_ivy()) end, desc = "Help Tags" },
    { "<leader>fq", function() require('telescope.builtin').quickfix(require('telescope.themes').get_ivy()) end, desc = "Quickfix List" },
    { "<leader>fl", function() require('telescope.builtin').loclist(require('telescope.themes').get_ivy()) end, desc = "Location List" },
    { "<leader>fj", function() require('telescope.builtin').jumplist(require('telescope.themes').get_ivy()) end, desc = "Jumplist" },
    { "<leader>fM", function() require('telescope.builtin').marks(require('telescope.themes').get_ivy()) end, desc = "Marks" },
    { "<leader>fk", function() require('telescope.builtin').keymaps(require('telescope.themes').get_ivy()) end, desc = "Keymaps" },
    { "<leader>fo", function() require('telescope.builtin').oldfiles(require('telescope.themes').get_ivy()) end, desc = "Old Files" },
    { "<leader>fc", function() require('telescope.builtin').command_history(require('telescope.themes').get_ivy()) end, desc = "Command History" },
    { "<leader>fs", function() require('telescope.builtin').search_history(require('telescope.themes').get_ivy()) end, desc = "Search History" },
    {
      "<leader>fh",
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
      desc = "Harpoon Window",
    },
  },
  config = function()
    local actions = require('telescope.actions')
    local trouble_ok, trouble = pcall(require, "trouble.sources.telescope")
    local open_with_trouble = trouble_ok and trouble.open or nil

    require('telescope').setup {
      defaults = {
        vimgrep_arguments = {
          require("config.machine").tool("rg"), "--color=never", "--no-heading",
          "--with-filename", "--line-number", "--column", "--smart-case",
        },
        wrap_results = true,
        layout_config = {
          vertical = { width = 0.5 },
        },
        file_ignore_patterns = {
          "node_modules",
          ".*.d.ts",
          "[.][/]dist.*",
        },
        mappings = {
          n = {
            ["<c-t>"] = open_with_trouble,
          },
          i = {
            ["<C-h>"] = "which_key",
            ["<C-j>"] = {
              actions.move_selection_next, type = "action",
              opts = { nowait = true, silent = true },
            },
            ["<c-t>"] = open_with_trouble,
            ["<C-k>"] = {
              actions.move_selection_previous, type = "action",
              opts = { nowait = true, silent = true },
            },
            ["<C-f>"] = {
              actions.move_selection_next, type = "action",
              opts = { nowait = true, silent = true },
            },
            ["<C-b>"] = {
              actions.move_selection_previous, type = "action",
              opts = { nowait = true, silent = true },
            },
          },
        },
      },
    }

    local machine = require("config.machine")
    if machine.get().features.native_fzf and machine.executable("cmake") then
      local ok = pcall(require('telescope').load_extension, "fzf")
      if not ok then machine.warn("Native FZF is unavailable; using Telescope's Lua sorter") end
    end

    vim.api.nvim_create_autocmd("User", {
      pattern = "TelescopePreviewerLoaded",
      callback = function()
        vim.wo.wrap = true
      end,
    })
  end,
}
