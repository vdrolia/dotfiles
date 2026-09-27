" A local vimrc can include this layer without duplicating its autocmds.
if exists('g:dotfiles_vim_loaded')
  finish
endif
let g:dotfiles_vim_loaded = 1

" Private settings load before plugin and tool configuration.
" An existing vimrc owns its implicit overlay; explicit selections still apply.
let s:coexist = get(g:, 'dotfiles_coexist', 0)
let s:local_config = !empty($DOTFILES_VIM_LOCAL) ? expand($DOTFILES_VIM_LOCAL) :
      \ (s:coexist ? '' : expand('~/.vimrc.local'))
if filereadable(s:local_config)
  execute 'source ' . fnameescape(s:local_config)
endif

let s:shell = get(g:, 'dotfiles_shell', empty($SHELL) ? &shell : $SHELL)
if executable(s:shell)
  let &shell = s:shell
endif
" Native detection handles unnamed buffers safely. Older Polyglot detection
" expands <afile>:e without a filename and errors during verbose startup.
" Keep its language packs; private settings may explicitly select another list.
let g:polyglot_disabled = get(g:, 'polyglot_disabled', ['ftdetect'])

" An existing vimrc owns plugin initialization unless explicitly enabled here.
let s:enable_plugins = get(g:, 'dotfiles_enable_plugins', !s:coexist)
if s:enable_plugins &&
      \ (exists('*plug#begin') || !empty(globpath(&runtimepath, 'autoload/plug.vim')))
call plug#begin(get(g:, 'dotfiles_plugins_dir', expand('~/.vim/plugged')))
Plug 'Valloric/YouCompleteMe'
Plug 'tpope/vim-endwise'
Plug 'google/vim-maktaba'
Plug 'google/vim-codefmt'
Plug 'google/vim-glaive'
Plug 'jiangmiao/auto-pairs'
Plug 'kien/ctrlp.vim'
Plug 'adelarsq/vim-matchit'
Plug 'mhinz/vim-signify'
Plug 'mileszs/ack.vim'
Plug 'ruby-formatter/rufo-vim'
Plug 'scrooloose/nerdtree'
Plug 'sheerun/vim-polyglot'
Plug 'tpope/vim-fugitive'
Plug 'tpope/vim-rails'
Plug 'tpope/vim-sleuth'
Plug 'tpope/vim-surround'
Plug 'vim-ruby/vim-ruby'
Plug 'vim-scripts/a.vim'
Plug 'ngmy/vim-rubocop'
Plug 'mlaursen/vim-react-snippets'
Plug 'joshdick/onedark.vim'
call plug#end()
endif

if s:enable_plugins && (exists('*glaive#Install') || !empty(globpath(&runtimepath, 'autoload/glaive.vim')))
  call glaive#Install()
endif

" Discover common installations; a private setting can select any other path.
let s:fzf_paths = exists('g:dotfiles_fzf_path') ? [g:dotfiles_fzf_path] :
      \ [$FZF_BASE, expand('~/.fzf'), '/opt/homebrew/opt/fzf', '/usr/local/opt/fzf', '/usr/share/fzf']
for s:fzf_path in s:fzf_paths
  if !empty(s:fzf_path) && isdirectory(s:fzf_path)
    execute 'set runtimepath+=' . fnameescape(s:fzf_path)
    break
  endif
endfor

syntax on
filetype plugin indent on
set hidden
set wildmenu
let mapleader = ","
set autoread
set lazyredraw

if exists('+clipboard')
  if exists('g:dotfiles_clipboard')
    let &clipboard = g:dotfiles_clipboard
  elseif has('clipboard') && (has('mac') || !empty($DISPLAY) || !empty($WAYLAND_DISPLAY))
    set clipboard+=unnamedplus
  endif
endif
set history=2500
set undolevels=2500
set title
set ruler
set nu
set tw=80
set nowrap
set timeoutlen=400

" Formatting
set ts=2
set bs=2
set shiftwidth=2
set incsearch
set autoindent
set smartindent
set smarttab
set smartcase
set expandtab
set lbr

" Visual
set showmatch
set mat=5
set novisualbell
set noerrorbells
set laststatus=2
set encoding=utf-8

" Backups & Files
set backup
let s:cache = empty($XDG_CACHE_HOME) ? expand('~/.cache') : $XDG_CACHE_HOME
let s:backupdir = expand(get(g:, 'dotfiles_backupdir', s:cache . '/vim/backups'))
let s:swapdir = expand(get(g:, 'dotfiles_swapdir', s:cache . '/vim/swap'))
for s:directory in [s:backupdir, s:swapdir]
  if !isdirectory(s:directory)
    call mkdir(s:directory, 'p', 0700)
  endif
endfor
" Direct option assignment preserves spaces; only list-separating commas escape.
let &backupdir = escape(s:backupdir, ',') . '//'
let &directory = escape(s:swapdir, ',') . '//'
set modelines=5

nnoremap <left> <nop>
nnoremap <right> <nop>
nnoremap <down> <nop>
nnoremap <up> <nop>
nnoremap ' `
nnoremap ` '

" ctrl-p
let g:ctrlp_custom_ignore = {
  \ 'dir': '\v[\/](\.DS_Store|src.assets|src.main.assets|ios.Images.xcassets|ios.Pods|ios.build|android.build|android.app.build|node_modules)$',
  \ 'file': '\v\.(git|hg|svn|jar|class|jar.original|ico|svg)$',
  \ }

let g:ctrlp_open_multiple_files = 'r'
nnoremap <Leader><space> :CtrlP<cr>
let g:ctrlp_cmd = 'CtrlP'
let g:ctrlp_working_path_mode = ''
set wildignore =*.o,*~,*.so,*.zip,*.swp,*.bak,*.pyc,*.class,*.iml,*.jar,*.class,*.jar.original
set wildignore +=*/.git/*,*/.hg/*,*/.svn/*,*/.DS_Store,*/ios/build/*,*/android/build/*,*/ios/Images.xcasset/*,*/dist/*
set wildignore +=*/.svg,*.ico

map <Leader>tt :tabnew %<cr>
map <Leader>tn :tabnext<cr>
map <Leader>tp :tabprevious<cr>
map <Leader>tc :tabclose<cr>
map <Leader>tm :tabmove

" Powerline
let g:Powerline_symbols = 'fancy'
if exists('+guifont') && exists('g:dotfiles_guifont')
  let &guifont = g:dotfiles_guifont
endif

set ffs=unix,mac

let g:rehash256 = 1

" YCM
let g:ycm_autoclose_preview_window_after_insertion = 1
let g:ycm_autoclose_preview_window_after_completion = 1
let g:ycm_key_list_select_completion = ['<C-j>', '<Down>']
let g:ycm_key_list_previous_completion = ['<C-k>', '<Up>']
let g:SuperTabDefaultCompletionType = '<C-n>'
let g:ycm_key_invoke_completion = '<C-Space>'
let g:ycm_auto_hover = ''
noremap <Leader>yr :YcmCompleter GoToReferences<CR>
noremap <C-I> :YcmCompleter GoToImplementation<CR>
noremap <C-]> :YcmCompleter GoToDefinitionElseDeclaration<CR>
noremap <C-F> :FormatCode<CR>
inoremap <C-F> <C-O>:FormatCode<CR>
vnoremap <C-F> :FormatLines<CR>
noremap <Leader>yR :YcmCompleter RefactorRename<cr>
noremap <Leader>yf :YcmCompleter FixIt<CR>
autocmd User YcmQuickFixOpened autocmd! ycmquickfix WinLeave

" Ack
noremap <Leader>a :Ack<cword><cr>

" Rails navigation
noremap <Leader>rc :Econtroller<cr>
noremap <Leader>rm :Emodel<cr>
noremap <Leader>re :Eenvironment<cr>
noremap <Leader>rh :Ehelper<cr>
noremap <Leader>rf :Efixtures<cr>
noremap <Leader>ra :A<cr>
noremap <Leader>rtu :Eunittest<cr>
noremap <Leader>rtf :Efunctionaltest<cr>
noremap <Leader>rd :Emigration<cr>
noremap <Leader>rs :Eschema<cr>
noremap <Leader>rv :Eview<cr>

" NERDTree
noremap <F3> :NERDTreeToggle<cr>

autocmd FileType yaml setlocal ts=2 sts=2 sw=2 expandtab

" vim-codefmt
if exists(':Glaive') == 2 && !empty(globpath(&runtimepath, 'autoload/codefmt.vim'))
  Glaive codefmt plugin[mappings]
  execute 'Glaive codefmt prettier_executable=' . string(get(g:, 'dotfiles_prettier_executable', 'prettier'))
  execute 'Glaive codefmt rubocop_executable=' . string(get(g:, 'dotfiles_rubocop_executable', 'rubocop'))
endif
let g:vimrubocop_rubocop_cmd = shellescape(get(g:, 'dotfiles_rubocop_executable', 'rubocop')) . ' '
autocmd BufNewFile,BufRead *.rb set filetype=ruby
autocmd BufNewFile,BufRead *.css set filetype=css
autocmd BufNewFile,BufRead *.html set filetype=html
autocmd BufNewFile,BufRead *.ts set filetype=typescript tabstop=2 softtabstop=2 shiftwidth=2 textwidth=80 expandtab fileformat=unix
autocmd BufNewFile,BufRead *.tsx set filetype=typescript
autocmd BufNewFile,BufRead *.json set filetype=json
autocmd BufNewFile,BufRead *.graphqls set filetype=graphql
autocmd FileType json,typescript,javascript,html,css let b:codefmt_formatter = 'prettier'
autocmd FileType graphql let b:codefmt_formatter = 'prettier'
autocmd FileType ruby let b:codefmt_formatter = 'rubocop'

" vim-signify
let g:signify_vcs_list = ['git']

" switch tabs (same as gt & gT)
nnoremap <C-j> :tabprevious<CR>
nnoremap <C-k> :tabnext<CR>

" Python
au BufNewFile,BufRead *.py set tabstop=4 softtabstop=4 shiftwidth=4 textwidth=79 expandtab autoindent fileformat=unix

if (empty($TMUX))
  if (has("nvim"))
    let $NVIM_TUI_ENABLE_TRUE_COLOR=1
  endif
  if (has("termguicolors"))
    set termguicolors
  endif
endif
if !empty(globpath(&runtimepath, 'colors/onedark.vim'))
  colorscheme onedark
endif

" Define this function in the private file for settings that must run last.
if exists('*DotfilesVimLocal')
  call DotfilesVimLocal()
endif
