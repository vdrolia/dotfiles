return {
  -- Git signs in gutter + hunk navigation + inline blame
  {
    "lewis6991/gitsigns.nvim",
    event = { "BufReadPost", "BufNewFile" },
    cond = function() return require("config.machine").executable("git") end,
    opts = {
      current_line_blame = true,
      current_line_blame_opts = { delay = 500 },
      on_attach = function(bufnr)
        local gs = require('gitsigns')
        local map = function(mode, l, r, desc)
          vim.keymap.set(mode, l, r, { buffer = bufnr, desc = 'Git: ' .. desc })
        end
        map('n', ']c', function() gs.nav_hunk('next') end, 'Next hunk')
        map('n', '[c', function() gs.nav_hunk('prev') end, 'Prev hunk')
        map('n', '<leader>gs', gs.stage_hunk, 'Stage hunk')
        map('n', '<leader>gr', gs.reset_hunk, 'Reset hunk')
        map('n', '<leader>gp', gs.preview_hunk, 'Preview hunk')
        map('n', '<leader>gb', gs.blame_line, 'Blame line')
        map('n', '<leader>gd', gs.diffthis, 'Diff this')
      end,
    },
  },

  -- Easypick — git-focused pickers
  {
    "axkirillov/easypick.nvim",
    cmd = { "Easypick", "GitChangedFiles" },
    cond = function() return require("config.machine").executable("git") end,
    dependencies = { "nvim-telescope/telescope.nvim" },
    config = function()
      -- Keep the original commands while resolving refs and preview paths without a shell.
      local names = { "git_changed_files", "git_conflicts" }
      local function open(name)
        require("config.git_picker").open(name == "git_conflicts")
      end
      vim.api.nvim_create_user_command("GitChangedFiles", function() open("git_changed_files") end, {})
      vim.api.nvim_create_user_command("Easypick", function(opts)
        if opts.args == "" then
          vim.ui.select(names, { prompt = "Git picker" }, function(name) if name then open(name) end end)
        elseif vim.tbl_contains(names, opts.args) then
          open(opts.args)
        else
          require("config.machine").warn("Unknown picker: " .. opts.args)
        end
      end, { nargs = "?", complete = function() return names end, force = true })
    end,
  },
}
