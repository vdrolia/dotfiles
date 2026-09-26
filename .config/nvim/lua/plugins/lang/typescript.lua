return {
  "pmizio/typescript-tools.nvim",
  ft = { "typescript", "javascript", "typescriptreact", "javascriptreact" },
  dependencies = { "nvim-lua/plenary.nvim", "neovim/nvim-lspconfig" },
  cond = function()
    return vim.fn.executable("node") == 1 and vim.fn.executable("npm") == 1
  end,
  opts = function()
    local settings = require("config.machine").get()
    return {
    -- The upstream provider asserts when tsserver is missing. Decline attachment
    -- gracefully; resolve again for each buffer so installing TypeScript later works.
    root_dir = function(bufnr, on_dir)
      local root = require("typescript-tools.utils").get_root_dir(bufnr)
      local candidates = {}
      if settings.tools.tsserver then
        table.insert(candidates, vim.fn.expand(settings.tools.tsserver))
      end
      for directory in vim.fs.parents(vim.api.nvim_buf_get_name(bufnr)) do
        table.insert(candidates, vim.fs.joinpath(directory, "node_modules", "typescript", "lib", "tsserver.js"))
        table.insert(candidates, vim.fs.joinpath(directory, ".yarn", "sdks", "typescript", "lib", "tsserver.js"))
      end
      table.insert(candidates, vim.fs.joinpath(vim.fn.expand(settings.paths.mason), "packages",
        "typescript-language-server", "node_modules", "typescript", "lib", "tsserver.js"))
      local executable = vim.fn.exepath("tsserver")
      if executable ~= "" then
        local prefix = vim.fs.dirname(vim.fs.dirname(vim.fn.resolve(executable)))
        table.insert(candidates, vim.fs.joinpath(prefix, "lib", "tsserver.js"))
        table.insert(candidates, vim.fs.joinpath(prefix, "lib", "node_modules", "typescript", "lib", "tsserver.js"))
      end
      for _, path in ipairs(candidates) do
        if vim.fn.filereadable(path) == 1 then on_dir(root); return end
      end
      vim.system({ "npm", "root", "-g" }, { text = true, timeout = 3000 }, function(result)
        vim.schedule(function()
          if not vim.api.nvim_buf_is_valid(bufnr) then return end
          local prefix = vim.trim(result.stdout or "")
          if result.code == 0 and prefix ~= "" and vim.fn.filereadable(
            vim.fs.joinpath(prefix, "typescript", "lib", "tsserver.js")) == 1 then
            on_dir(root)
          else
            vim.notify_once("TypeScript LSP needs project TypeScript, Mason typescript-language-server, or tools.tsserver", vim.log.levels.WARN)
          end
        end)
      end)
    end,
    settings = {
      tsserver_max_memory = settings.resource_limits.typescript_memory_mb,
      tsserver_path = settings.tools.tsserver and vim.fn.expand(settings.tools.tsserver) or nil,
      complete_function_calls = true,
      -- Disable formatting — handled by eslint/conform
      tsserver_file_preferences = {
        disableSuggestions = false,
      },
    },
    on_init = function(client)
      client.server_capabilities.documentFormattingProvider = false
      client.server_capabilities.documentRangeFormattingProvider = false
    end,
    }
  end,
}
