local machine = require("config.machine")
local settings = machine.get()
-- Retain Neovim's platform default unless a complete local shell override is set.
if settings.shell.command and vim.fn.executable(settings.shell.command) ~= 1 then
  machine.warn("Configured shell is not executable; retaining all platform shell defaults")
else
  for key, value in pairs(settings.shell) do
    local option = key == "command" and "shell" or "shell" .. key
    vim.opt[option] = value
  end
end

vim.opt.autoread = true
vim.opt.lazyredraw = false

-- Defer clipboard to avoid synchronous provider detection at startup
if settings.clipboard.provider then vim.g.clipboard = settings.clipboard.provider end
if settings.clipboard.enabled then
  vim.schedule(function() vim.opt.clipboard:append(settings.clipboard.mode) end)
end

vim.opt.history = 2500
vim.opt.undolevels = 2500
vim.opt.title = true
vim.opt.ruler = true
vim.opt.number = true
vim.opt.textwidth = 80
vim.opt.wrap = false
vim.opt.timeoutlen = 400

vim.opt.tabstop = 2
vim.opt.softtabstop = 2
vim.opt.backspace = { 'indent', 'eol', 'start' }
vim.opt.shiftwidth = 2
vim.opt.incsearch = true
vim.opt.autoindent = true
vim.opt.smartindent = true
vim.opt.smarttab = true
vim.opt.smartcase = true
vim.opt.expandtab = true
vim.opt.linebreak = true
vim.opt.showmatch = true
vim.opt.matchtime = 5
vim.opt.visualbell = false
vim.opt.errorbells = false
vim.opt.laststatus = 2
vim.opt.encoding = 'utf-8'
vim.opt.cursorline = true

-- Backup directory with auto-creation
local backupdir = vim.fn.expand(settings.paths.backup)
if vim.fn.isdirectory(backupdir) == 0 then
  vim.fn.mkdir(backupdir, 'p')
end
vim.opt.backup = true
vim.opt.backupdir = { backupdir .. "//" }
vim.opt.modelines = 5

vim.opt.wildignore:append {
  '*.o', '*~', '*.so', '*.zip', '*.swp', '*.bak', '*.pyc', '*.class',
  '*.iml', '*.jar', '*.jar.original', '*/.git/*', '*/.hg/*', '*/.svn/*',
  '*/.DS_Store', '*/node_modules/*', '*/ios/build/*', '*/android/build/*',
  '*/ios/Images.xcasset/*', '*/dist/*', '*.svg', '*.ico',
}
vim.opt.fileformats = { 'unix', 'dos', 'mac' }
