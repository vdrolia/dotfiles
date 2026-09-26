local M = {}

-- Frozen Treesitter requires grammar generation for some languages (e.g. Swift).
-- Missing optional tools must not turn opening a file into an installation error.
function M.installable(requested, definitions)
  local machine = require("config.machine")
  local settings = machine.get()
  if not settings.features.auto_install then return {} end
  if not machine.has_compiler() or (vim.fn.executable("curl") == 0 and vim.fn.executable("git") == 0) then
    machine.warn("Parser installation needs a C compiler and curl or Git; using installed parsers")
    return {}
  end
  definitions = definitions or require("nvim-treesitter.parsers").get_parser_configs()
  local cli_compatible
  local function has_cli()
    if cli_compatible ~= nil then return cli_compatible end
    cli_compatible = false
    if vim.fn.executable("tree-sitter") == 1 then
      local result = vim.system({ "tree-sitter", "--version" }, { text = true }):wait(2000)
      local major, minor = (result.stdout or ""):match("tree%-sitter (%d+)%.(%d+)")
      cli_compatible = result.code == 0 and tonumber(major) == 0 and tonumber(minor) <= 25
    end
    return cli_compatible
  end
  local available = {}
  for _, language in ipairs(requested) do
    local info = definitions[language] and definitions[language].install_info
    local missing
    if not info then
      missing = "a parser supported by the pinned Treesitter version"
    elseif info.requires_generate_from_grammar then
      if not has_cli() then missing = "tree-sitter CLI <=0.25.x on PATH"
      elseif vim.fn.executable("node") == 0 then missing = "Node.js on PATH"
      elseif info.generate_requires_npm and vim.fn.executable("npm") == 0 then missing = "npm on PATH" end
    end
    if missing then
      machine.warn("Skipping parser installation/update for " .. language .. ": needs " .. missing)
    else
      table.insert(available, language)
    end
  end
  return available
end

return M
