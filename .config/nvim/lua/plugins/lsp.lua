return {
	-- LSP Configuration
	{
		"neovim/nvim-lspconfig",
        lazy = false,
		dependencies = {
			"williamboman/mason.nvim",
			"williamboman/mason-lspconfig.nvim",
			"WhoIsSethDaniel/mason-tool-installer.nvim",
			"hrsh7th/cmp-nvim-lsp",
		},
		config = function()
			local ok_mason, mason = pcall(require, "mason")
			local ok_mlc, mason_lspconfig = pcall(require, "mason-lspconfig")
			local ok_mti, mason_tool_installer = pcall(require, "mason-tool-installer")
			if not (ok_mason and ok_mlc and ok_mti) then
				vim.notify("Mason dependencies failed to load", vim.log.levels.ERROR)
				return
			end

            local machine = require("config.machine")
            local settings = machine.get()
            -- Mason must establish PATH before resolving formatter/server binaries.
            mason.setup({ install_root_dir = vim.fn.expand(settings.paths.mason) })
            local capabilities = require("cmp_nvim_lsp").default_capabilities()
            local server_options = {
                lua_ls = { settings = { Lua = { diagnostics = { globals = { "vim" } } } } },
                gopls = {
                    cmd = { machine.tool("gopls") },
                    settings = { gopls = {
                        completeUnimported = true, usePlaceholders = true,
                        analyses = { unusedparams = true, unusedvariable = true }, staticcheck = true,
                    } },
                },
                eslint = {
                    cmd_env = { NODE_OPTIONS = machine.node_options(settings.resource_limits.eslint_memory_mb) },
                    settings = { format = true },
                },
                basedpyright = { settings = { basedpyright = {
                    analysis = { typeCheckingMode = "standard", autoImportCompletions = true },
                    disableOrganizeImports = true,
                } } },
                ruff = { on_attach = function(client) client.server_capabilities.hoverProvider = false end },
            }
            local names = {}
            for _, name in ipairs(settings.servers.ensure_installed) do names[name] = true end
            for name in pairs(settings.servers.configs) do names[name] = true end
            -- Mason 2 enables servers through Neovim 0.11; its former handlers API is gone.
            -- Register all overrides BEFORE Mason can enable an installed server.
            for name in pairs(names) do
                vim.lsp.config(name, vim.tbl_deep_extend("force",
                    { capabilities = capabilities }, server_options[name] or {},
                    settings.servers.configs[name] or {}))
            end
            if settings.features.auto_install then
                mason_tool_installer.setup({
                    ensure_installed = settings.tools.ensure_installed,
                })
                mason_lspconfig.setup({
                    ensure_installed = settings.servers.ensure_installed,
                    -- Its package supplies tsserver; typescript-tools owns the client.
                    automatic_enable = { exclude = { "ts_ls" } },
                })
            end
            -- Also enable configured servers installed outside Mason. With auto_install
            -- disabled, this path avoids any registry refresh or network request.
            for name in pairs(names) do
                local config = vim.lsp.config[name]
                local cmd = config and config.cmd
                if type(cmd) == "function" or (type(cmd) == "table" and vim.fn.executable(cmd[1]) == 1) then
                    vim.lsp.enable(name)
                end
            end

			-- LspAttach autocmd with capability checks
			vim.api.nvim_create_autocmd("LspAttach", {
				group = vim.api.nvim_create_augroup("lsp-attach", { clear = true }),
				callback = function(event)
					local client = vim.lsp.get_client_by_id(event.data.client_id)
					if not client then
						return
					end

					local map = function(keys, func, desc, mode)
						mode = mode or "n"
						vim.keymap.set(mode, keys, func, { buffer = event.buf, desc = "LSP: " .. desc })
					end

					-- Navigation (supplements Neovim 0.11 built-in: grn, gra, grr, gri, K, [d, ]d)
					if client:supports_method("textDocument/definition") then
						map("gd", vim.lsp.buf.definition, "Go to definition")
					end
					if client:supports_method("textDocument/declaration") then
						map("gD", vim.lsp.buf.declaration, "Go to declaration")
					end
					if client:supports_method("textDocument/typeDefinition") then
						map("<leader>ct", vim.lsp.buf.type_definition, "Type definition")
					end
					if client:supports_method("textDocument/signatureHelp") then
						map("<C-s>", vim.lsp.buf.signature_help, "Signature help", "i")
					end

					-- ESLint-specific: auto-fix on save
					if client.name == "eslint" then
						vim.api.nvim_create_autocmd("BufWritePre", {
							buffer = event.buf,
							callback = function()
                                local ok_fix, err = pcall(vim.cmd, "LspEslintFixAll")
								if not ok_fix then
                                    vim.notify("LspEslintFixAll failed: " .. tostring(err), vim.log.levels.WARN)
								end
							end,
						})
					end
				end,
			})
		end,
	},

	-- Completion
	{
		"hrsh7th/nvim-cmp",
		event = "InsertEnter",
		dependencies = {
			"hrsh7th/cmp-nvim-lsp",
			"hrsh7th/cmp-buffer",
			"hrsh7th/cmp-path",
			"L3MON4D3/LuaSnip",
            "saadparwaiz1/cmp_luasnip",
		},
		config = function()
			local cmp = require("cmp")
			local luasnip = require("luasnip")

			local kind_icons = {
				Text = "󰉿",
				Method = "󰆧",
				Function = "󰊕",
				Constructor = "󰒓",
				Field = "󰇽",
				Variable = "󰂡",
				Class = "󰠱",
				Interface = "󰼮",
				Module = "󰏗",
				Property = "󰜢",
				Unit = "󰑭",
				Value = "󰎠",
				Enum = "󰎦",
				Keyword = "󰌋",
				Snippet = "󰌍",
				Color = "󰏘",
				File = "󰈙",
				Reference = "󰈇",
				Folder = "󰉋",
				EnumMember = "󰦨",
				Constant = "󰏿",
				Struct = "󰙅",
				Event = "󰕘",
				Operator = "󰆕",
				TypeParameter = "󰅲",
			}

			cmp.setup({
				snippet = {
					expand = function(args)
						luasnip.lsp_expand(args.body)
					end,
				},
				window = {
					completion = cmp.config.window.bordered(),
					documentation = cmp.config.window.bordered(),
				},
				formatting = {
					format = function(entry, vim_item)
                        if require("config.machine").get().icons.enabled then
                            vim_item.kind = (kind_icons[vim_item.kind] or "") .. " " .. vim_item.kind
                        end
						vim_item.menu = ({
							nvim_lsp = "[LSP]",
							luasnip = "[Snip]",
							buffer = "[Buf]",
							path = "[Path]",
						})[entry.source.name]
						return vim_item
					end,
				},
				sources = cmp.config.sources({
					{ name = "nvim_lsp" },
					{ name = "luasnip" },
				}, {
					{ name = "buffer", keyword_length = 3 },
					{ name = "path" },
				}),
				mapping = cmp.mapping.preset.insert({
					["<CR>"] = cmp.mapping.confirm({ select = false }),
					["<C-Space>"] = cmp.mapping.complete(),
					["<C-u>"] = cmp.mapping.scroll_docs(-4),
					["<C-d>"] = cmp.mapping.scroll_docs(4),
					["<C-f>"] = cmp.mapping(function(fallback)
						if luasnip.jumpable(1) then
							luasnip.jump(1)
						else
							fallback()
						end
					end, { "i", "s" }),
					["<C-b>"] = cmp.mapping(function(fallback)
						if luasnip.jumpable(-1) then
							luasnip.jump(-1)
						else
							fallback()
						end
					end, { "i", "s" }),
				}),
			})
		end,
	},

	-- Neoconf — per-project settings
	{ "folke/neoconf.nvim", cmd = "Neoconf" },
}
