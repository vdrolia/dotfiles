# Dotfiles

Shared shell, Git, Vim, Neovim, and tmux preferences. Personal identities,
machine names, credentials, and application state belong in private files
outside this checkout. Claude configuration, skills, and knowledge are managed
separately and are not installed or synchronized here.

## Installation

Requires Bash, Python 3.9+, Git, and POSIX symlinks. Targets macOS and Linux/WSL;
native Windows installation is unsupported. Install applications separately.

```sh
./install.sh --dry-run
./install.sh
```

Automatic pushes are disabled on new clones, including work machines. Normal
installation and `--install-hooks` do not enable them. Reinstalling preserves a
clone's existing explicit choice.

Only `install-manifest.json` entries are installed. Shared configuration files
become symlinks. Tool versions, htop settings, and Flipper settings become
writable local copies seeded from `templates/`. Existing local contents are
preserved, including when detaching an old file symlink.

Replaced files receive unique private backups under
`${XDG_STATE_HOME:-$HOME/.local/state}/dotfiles/backups/`. Each backup includes a
manifest of destinations, previous symlink targets, and saved contents.
Repeated installation preserves existing local copies. Previewing performs no
writes. Directory symlinks routing writes into the checkout must be migrated first.

```sh
./install.sh --target-dir /path/to/test-home --config-dir /path/to/test-config
```

`DOTFILES_TARGET_DIR` and `DOTFILES_CONFIG_DIR` provide the same overrides.
For the real home, `XDG_CONFIG_HOME` selects the configuration root. An alternate
target defaults to its own `.config` and `.local/state`. XDG directory variables
must be absolute. Private overrides default to
`${XDG_CONFIG_HOME:-$HOME/.config}/dotfiles`; `DOTFILES_LOCAL_DIR` or the
installer's `--local-dir` selects another private directory. Applications must
receive the corresponding environment setting for a custom location.

## Private configuration

Copy the examples you need to these locations, edit the copies, and keep them
outside this checkout. The installer does not generate identities or overwrite
these files. Restrict private files with `chmod 600`.

| Private location | Example | Loading behavior |
| --- | --- | --- |
| `~/.gitconfig.local` | `examples/gitconfig.local.example` | Git native include: identity, signing, transport, pager, LFS, conditional includes |
| `$DOTFILES_LOCAL_DIR/env.zsh` | `examples/env.zsh.example` | Before shell paths, plugins, completion, and tool initialization |
| `~/.zshrc-local` | `examples/zshrc-local.example` | After shared functions/aliases; `DOTFILES_ZSH_LOCAL` selects another file |
| `~/.vimrc.local` | `examples/vimrc.local.example` | Early `g:dotfiles_*` variables, then final `DotfilesVimLocal()` callback; `DOTFILES_VIM_LOCAL` selects another file |
| `~/.tmux.conf.local` | `examples/tmux.conf.local.example` | After shared settings; `DOTFILES_TMUX_LOCAL` selects another file |
| `$DOTFILES_LOCAL_DIR/nvim.lua` | `examples/nvim.lua.example` | Lua table before options/plugins; `DOTFILES_NVIM_LOCAL` takes precedence |
| `$DOTFILES_LOCAL_DIR/flipper.json` | `examples/flipper.local.json.example` | Applied only by explicit Flipper rendering |

Git requires an explicit identity (`user.useConfigOnly=true`). A private include
hides the source file, but author/committer names and emails still appear in
commits. GitHub noreply addresses identify accounts too. For deliberately
anonymous publication, choose an appropriate public pseudonym and placeholder
address such as `public@example.invalid` in the publication repository. Review
commit metadata before pushing.

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
| Neovim lockfile | Public dependency revisions. Compatibility requires tested pins and per-platform builds, not environment substitution. |

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
./install.sh --install-hooks --dry-run
./install.sh --install-hooks
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
./install.sh --enable-auto-sync --dry-run
./install.sh --enable-auto-sync
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
./install.sh --disable-auto-sync --dry-run
./install.sh --disable-auto-sync
```

Disabling sets clone-local `dotfiles.autoSync=false` and preserves existing hooks,
including unrelated custom hooks. GitHub access controls and branch/tag rules
enforce publication permissions; keep write access limited to the repository
owner. Local hooks do not grant or enforce remote permissions. Public access lets
others clone, fork, and use these dotfiles without granting push access.

Run `python3 -B -m unittest discover -s tests -v` for isolated tests.
See `tests/README.md` for integration-test requirements.
