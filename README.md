# Dotfiles

Shared shell, Git, Vim, Neovim, and tmux preferences. Personal identities,
machine names, credentials, and application state belong in private files
outside this checkout. Claude configuration, skills, and knowledge are managed
separately and are not installed or synchronized here.

## Installation

Requires Bash, Python 3.9+, Git, and POSIX symlinks. Targets macOS and Linux/WSL;
native Windows installation is unsupported. Install applications separately.
Keep this checkout anywhere you like; it does not claim `~/.dotfiles` or require
you to rename or replace an existing dotfiles repository.

For a machine that already has its own setup, choose the components to add:

```sh
./install.sh --list-components
./install.sh --components zsh,git --dry-run
./install.sh --components zsh,git
```

The default mode is modular. Omitting `--components` selects all components:

```sh
./install.sh --dry-run
./install.sh
```

Automatic pushes are disabled on new clones, including work machines. Normal
installation and `--install-hooks` do not enable them. Reinstalling preserves a
clone's existing explicit choice.

Only selected `install-manifest.json` entries are installed. Shared settings
load first; your existing settings load afterward and retain precedence.

| Component | Modular installation |
| --- | --- |
| `zsh` | Add a managed source block to the active `.zshrc`. Existing setup keeps ownership of framework initialization. Helpers load beside the shared source; no separate home helper file is needed. |
| `git` | Add a native include before existing global Git settings. Existing workplace identities and conditional includes remain authoritative. |
| `vim` | Add a source block before existing Vim settings. Existing setup keeps ownership of plugin-manager initialization. |
| `tmux` | Add a source block before existing tmux settings. |
| `nvim` | Install a separate `dotfiles-nvim` profile and launcher; ordinary `nvim` keeps its existing configuration. |
| `ack`, `tools`, `htop`, `flipper` | Seed a configuration only when missing. Existing files and symlinks remain intact. |

Regular configuration files retain their existing contents outside the managed
block. A symlink to another setup becomes a small local wrapper that sources
the original target after the shared settings; the other repository's file is
never edited, and later changes to it still load. A symlink already pointing
into this checkout becomes a direct include without loading it twice.
Reinstalling updates the managed block without duplicating it. Component
selection affects installation; it does not uninstall previously selected apps.
Use `--components none` when configuring only this checkout's Git hooks or sync.
Shared shell and Vim settings load once per session; start a fresh shell or Vim
process after changing them. Existing local settings still load after the block.

Directory symlinks that would route writes into another Git worktree are
rejected before changes. Add a native include in that setup yourself, or choose
an entrypoint outside it with the path options below. The installer does not
merge arbitrary plugin managers, configuration languages, or application state.

Replaced files receive unique private backups under
`${XDG_STATE_HOME:-$HOME/.local/state}/dotfiles/backups/`. Each backup includes a
manifest of destinations, previous symlink targets, and saved contents.
Repeated installation preserves existing local copies. Previewing performs no
writes. To stop loading a module, remove its marked include block. A wrapper
continues to load its original configuration; the backup manifest also records
the previous symlink if you want to restore it.

```sh
./install.sh --target-dir /path/to/test-home --config-dir /path/to/test-config
```

`DOTFILES_TARGET_DIR` and `DOTFILES_CONFIG_DIR` provide the same overrides.
For the real home, `XDG_CONFIG_HOME` selects the configuration root. An alternate
target defaults to its own `.config` and `.local/state`. XDG directory variables
must be absolute. Zsh respects `ZDOTDIR` for the real home; `--zsh-dir` selects
another startup directory. `--git-config`, `--vim-config`, and `--tmux-config`
select explicit entrypoints. Git and tmux reuse their existing native locations
instead of creating a higher-priority file that hides them. Private overrides default to
`${XDG_CONFIG_HOME:-$HOME/.config}/dotfiles`; `DOTFILES_LOCAL_DIR` or the
installer's `--local-dir` selects another private directory.

The former link-based installation remains available explicitly for a machine
where this repository owns the configuration:

```sh
./install.sh --mode link --dry-run
./install.sh --mode link
```

This mode replaces selected entrypoints with shared links after backing them
up. Git uses an include wrapper so private identity configuration still loads.
Neovim uses the standard `nvim` configuration in link mode. Prefer modular mode
on a work machine or when another setup already manages these applications.

## Private configuration

Copy the examples you need to these locations, edit the copies, and keep them
outside this checkout. The installer does not generate identities or overwrite
these files. Restrict private files with `chmod 600`.

| Private location | Example | Loading behavior |
| --- | --- | --- |
| `~/.gitconfig.local` | `examples/gitconfig.local.example` | Clean/previously owned Git entrypoints include this file; existing unrelated Git setups keep their own identity includes |
| `$DOTFILES_LOCAL_DIR/env.zsh` | `examples/env.zsh.example` | Before shell paths, plugins, completion, and tool initialization |
| `~/.zshrc-local` | `examples/zshrc-local.example` | After shared functions/aliases in standalone setup; `DOTFILES_ZSH_LOCAL` explicitly selects a file in either mode |
| `~/.vimrc.local` | `examples/vimrc.local.example` | Early variables and final `DotfilesVimLocal()` callback in standalone setup; `DOTFILES_VIM_LOCAL` explicitly selects a file |
| `~/.tmux.conf.local` | `examples/tmux.conf.local.example` | After shared settings in standalone setup; `DOTFILES_TMUX_LOCAL` explicitly selects a file |
| `$DOTFILES_LOCAL_DIR/nvim.lua` | `examples/nvim.lua.example` | Lua table before options/plugins; `DOTFILES_NVIM_LOCAL` takes precedence |
| `$DOTFILES_LOCAL_DIR/flipper.json` | `examples/flipper.local.json.example` | Applied only by explicit Flipper rendering |

Git requires an explicit identity (`user.useConfigOnly=true`). A private include
hides the source file, but author/committer names and emails still appear in
commits. GitHub noreply addresses identify accounts too. For deliberately
anonymous publication, choose an appropriate public pseudonym and placeholder
address such as `public@example.invalid` in the publication repository. Review
commit metadata before pushing.

When layering into an existing setup, implicit shell/Vim/tmux local files stay
under that setup's control. Set the corresponding explicit override variable
to load a particular file through this layer. The existing configuration still
loads afterward. Reinstallation preserves whether the layer was originally
standalone or added to another setup, including after you add local settings.

The shell skips unavailable optional plugins. Set `DOTFILES_BREW_PREFIX` in the
early private file when Homebrew is not yet on PATH. Both legacy asdf scripts
and current asdf executables are supported. Locale is inherited unless
`DOTFILES_LOCALE` is set. AWS/Jira credentials stay in native private stores.
EC2 helpers take a name argument or `DOTFILES_EC2_NAME` and reject ambiguous
matches. Branch names are opaque by default; `DOTFILES_BRANCH_TICKET_CONTEXT=1`
deliberately permits ticket keys and summaries in potentially public branch names.

Vim works without vim-plug; installing its optional plugins is a separate step.
tmux detects terminfo and clipboard capabilities. Private settings can override
font, shell, terminal, clipboard, backup locations, and tool paths. Existing
tmux servers need their configuration reloaded to apply changes.

## Neovim

Modular installation gives this configuration its own command:

```sh
./install.sh --components nvim
~/.local/bin/dotfiles-nvim
```

The launcher selects `NVIM_APPNAME=dotfiles-nvim`, with separate configuration,
plugin data, state, and cache. It leaves ordinary `nvim` and its files untouched.
`--nvim-profile` selects another profile/launcher name; `nvim` is reserved for
the existing setup. Unrelated files at the selected profile are rejected.
The profile's lockfile is seeded as a local copy, so routine plugin updates do
not write into this Git checkout. Review and copy intentional pin changes back
to the repository before publishing. Private Lua settings remain shared through
`DOTFILES_LOCAL_DIR`; explicit private paths may deliberately share resources.
Launch a GUI through the same wrapper or supply the same profile and config root.

Requires Neovim 0.11.3–0.11.x; the pinned suite is tested on 0.11.6. Compatible
Treesitter master and Go 0.11 release pins are used. Keep editor/plugin API
compatibility in mind when updating; these frozen Treesitter pins do not support
Neovim 0.12. Mason uses `vim.lsp.config` before enabling
language servers.

Private Lua exposes shell/clipboard/icon choices, paths, executable locations,
formatter/server/parser lists, memory limits, and feature toggles. `paths.bin`
adds private executable directories for plugins that use command names via PATH.
Use absolute executable paths or expand them explicitly with `vim.fn.expand`;
command strings do not receive general shell expansion. Default data
and backup locations use Neovim standard paths. GUI launches load the private
Lua file without an interactive shell. Project Python and the interpreter
containing debugpy are separate settings. Git pickers resolve the current
repository at invocation and pass argument lists to Git; configure
`tools.git_base_branch` if `origin/HEAD` is absent.

First startup can download lazy.nvim/plugins and Mason tools and compile parsers.
Some parsers, including Swift, need a compatible Tree-sitter CLI (up to 0.25.x)
and Node.js; parsers with unmet prerequisites are skipped with a warning.
Native Telescope FZF requires CMake and a C compiler; the Lua sorter is the
fallback. For separately managed/offline dependencies, set
`features.bootstrap=false` and `features.auto_install=false` in private Lua.
`features.native_fzf=false` skips the native extension. Missing optional tools
are skipped or reported. Plugin pins do not pin all external runtimes, Mason
packages, or platform-specific compiled artifacts.

Back up an existing plugin data directory before applying pins with `:Lazy restore`.
Rebuild native extensions/parsers per platform; do not copy binaries between OSes.

## Formats without native overlays

| Configuration | Approach and limitation |
| --- | --- |
| asdf | Local `~/.tool-versions`, seeded once. `.tool-versions.local` is not included automatically; environment version overrides also override project pins. |
| htop | Local writable config, seeded once. `HTOPRC` selects another file. htop can rewrite its config. |
| Flipper | Local writable JSON. Explicit rendering recursively merges template, existing settings, then private overrides. JSON does not expand shell variables. |
| Ack | `ACKRC` selects a different user config instead of appending an overlay. Use a private complete config or project `.ackrc`. No general shell expansion. |
| Neovim lockfile | Public pins seed a private profile lockfile in modular mode. Compatibility requires tested revisions and per-platform builds. |

Deliberately apply Flipper overrides with:

```sh
./install.sh --render-flipper --dry-run
./install.sh --render-flipper
# Or select a private JSON object explicitly:
./install.sh --flipper-overrides /path/to/private/flipper.json
```

Unrelated existing application state is preserved; array/scalar overrides replace
old values. Normal installation preserves existing regular Flipper settings files.

## Privacy checks

Install Gitleaks separately. The checker also requires Git with `--no-lazy-fetch`
support (tested with Git 2.51.2); older unsupported Git fails closed. Check all
current publication candidates:

```sh
python3 scripts/check-public.py
```

The checker requires Gitleaks and checks emails, home paths, private network
addresses, prohibited files, filenames, and a personal denylist. Set
`DOTFILES_PRIVACY_DENYLIST` to an external UTF-8 file containing one literal
identifier per line: names, usernames, organizations, hostnames, account IDs,
private domains, or other strings to keep private. Matching ignores case; blank
lines and lines beginning with `#` are ignored. Export this variable from private
shell configuration. Findings report locations/categories without printing
matched values. Checks cannot recognize every personal fact without review.

When `DOTFILES_PRIVACY_DENYLIST` is unset, an existing `privacy-denylist.txt` in
`DOTFILES_LOCAL_DIR` is loaded automatically, defaulting to
`${XDG_CONFIG_HOME:-$HOME/.config}/dotfiles`. Its resolved path must be outside the
checkout. An explicitly configured missing file blocks publication.

To deliberately attribute commits to a public account, create a private
`public-identities.json` beside the denylist, or select an external file with
`DOTFILES_PUBLIC_IDENTITIES`. Its schema is an array of exact name/email pairs:

```json
[{"name": "Your approved public name", "email": "public@example.invalid"}]
```

Use the exact identity you intend to publish. A GitHub account's verified email
or GitHub-provided noreply address can link commits to that account; approving
it intentionally permits that public association. Approval applies only to
structured author/committer identity fields in actual commit objects. File
contents, commit messages, ref names, taggers, and other metadata remain checked
against the full privacy rules. Gitleaks always scans the original bytes.
Without a policy, checks stay strict. Malformed or explicitly missing policies,
and policies resolving inside the checkout, block publication. Keep the policy
private; it is also rejected if force-added to Git.

Install optional Git hooks explicitly, with backups of replaced hooks:

```sh
./install.sh --components none --install-hooks --dry-run
./install.sh --components none --install-hooks
```

Custom `core.hooksPath` requires explicit integration with existing hooks.
Pre-commit checks the exact staged snapshot. Pre-push checks outgoing commit
trees, intermediate commits, published ref names, and tag/commit metadata.
New remote refs scan their full reachable history. These check-only hooks never
initiate commits, pushes, scheduled synchronization, or network requests. They
are local safeguards and can be bypassed, so review publication separately.

Cleaning current files does not sanitize history, hosted refs, pull requests,
or commit metadata. Use a reviewed clean export and newly initialized repository
when historical data must remain private. Do not change an old private repo's
visibility based only on a current-file scan.

## Optional automatic pushes

On a trusted machine, explicitly opt this clone into pushing commits you create:

```sh
./install.sh --components none --enable-auto-sync --dry-run
./install.sh --components none --enable-auto-sync
```

This installs the privacy pre-commit/pre-push hooks and a post-commit hook,
backing up replaced hooks, then sets clone-local `dotfiles.autoSync=true`.
An existing custom `core.hooksPath` requires manual integration. Dry runs change
neither hooks nor Git configuration. Hooks and the opt-in setting are not
inherited by new clones; a global setting cannot enable this feature.

After a deliberate commit, the hook requires an attached branch with a configured
upstream and pins its current commit. It scans that commit's full reachable history
before any network request, then attempts a normal push of that exact commit to
the upstream branch. It never stages files, creates commits, pulls, force-pushes,
or pushes tags or submodules.
A blocked or failed push leaves the commit saved locally and prints a warning.
Set the desired upstream with a deliberate initial push before relying on this
feature. Its remote must have exactly one push destination. The privacy checker
and Gitleaks must be installed and available.

Turn automatic pushes off for this clone with:

```sh
./install.sh --components none --disable-auto-sync --dry-run
./install.sh --components none --disable-auto-sync
```

Disabling sets clone-local `dotfiles.autoSync=false` and preserves existing hooks,
including unrelated custom hooks. GitHub access controls and branch/tag rules
enforce publication permissions; keep write access limited to the repository
owner. Local hooks do not grant or enforce remote permissions. Public access lets
others clone, fork, and use these dotfiles without granting push access.

Run `python3 -B -m unittest discover -s tests -v` for isolated tests.
See `tests/README.md` for integration-test requirements.
