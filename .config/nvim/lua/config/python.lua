local M = {}

local function interpreter(root)
  local suffix = vim.fn.has("win32") == 1 and { "Scripts", "python.exe" } or { "bin", "python" }
  return vim.fs.joinpath(root, unpack(suffix))
end

function M.debugpy()
  local settings = require("config.machine").get()
  local python = settings.tools.debugpy_python
  if type(python) == "function" then python = python() end
  python = python or interpreter(vim.fs.joinpath(vim.fn.expand(settings.paths.mason), "packages", "debugpy", "venv"))
  if vim.fn.executable(python) == 1 then return python end
  return nil, "Debugpy's interpreter is missing; install debugpy or set tools.debugpy_python"
end

function M.project(root)
  local python = require("config.machine").get().tools.python
  if type(python) == "function" then python = python(root or vim.fn.getcwd()) end
  if python then
    if vim.fn.executable(python) == 1 then return python end
    error("Configured project Python is not executable")
  end
  for _, variable in ipairs({ "VIRTUAL_ENV", "CONDA_PREFIX" }) do
    local root = vim.env[variable]
    if root and root ~= "" and vim.fn.executable(interpreter(root)) == 1 then return interpreter(root) end
  end
  for _, command in ipairs({ "python3", "python" }) do
    if vim.fn.executable(command) == 1 then return vim.fn.exepath(command) end
  end
  return nil
end

function M.setup_dap()
  local dap_python = require("dap-python")
  -- Setup registers commands/configurations, but does not start an interpreter.
  local opts = {}
  if require("config.machine").get().tools.python then
    opts.pythonPath = function() return M.project() end
  end
  -- Without a private override, retain upstream .venv/venv and project discovery.
  dap_python.setup("python3", opts)
  local dap = require("dap")
  local original_adapter = dap.adapters.python
  local adapter = function(callback, config)
    local python, err
    if config.request ~= "attach" then
      python, err = M.debugpy() -- Mason may have finished installing since plugin load.
      if not python then require("config.machine").warn(err); return end
    end
    original_adapter(function(spec)
      if spec.type == "executable" then spec.command = python end
      callback(spec)
    end, config)
  end
  dap.adapters.python = adapter
  dap.adapters.debugpy = adapter
end

return M
