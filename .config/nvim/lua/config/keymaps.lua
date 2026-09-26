local map = vim.api.nvim_set_keymap
local opts = { noremap = true }

-- Disable arrow keys in normal mode
map('n', '<left>', '<nop>', opts)
map('n', '<right>', '<nop>', opts)
map('n', '<down>', '<nop>', opts)
map('n', '<up>', '<nop>', opts)

-- Swap tick and backtick (backtick goes to exact mark position)
map('n', "'", '`', opts)
map('n', "`", "'", opts)
