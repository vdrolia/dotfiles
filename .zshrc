# The shared layer may be included by several local startup files.
(( ${+_dotfiles_zsh_loaded} )) && return 0
typeset -g _dotfiles_zsh_loaded=1

# Machine settings must load before paths, plugins, and completion scripts.
export DOTFILES_LOCAL_DIR="${DOTFILES_LOCAL_DIR:-${XDG_CONFIG_HOME:-$HOME/.config}/dotfiles}"
[[ -r "$DOTFILES_LOCAL_DIR/env.zsh" ]] && source "$DOTFILES_LOCAL_DIR/env.zsh"
typeset _dotfiles_source_dir="${${(%):-%N}:A:h}"
typeset _dotfiles_frameworks_enabled="${DOTFILES_ZSH_FRAMEWORKS:-1}"

# --- PATH ---
typeset -U path
# Existing configurations own their framework defaults in coexistence mode.
if [[ "$_dotfiles_frameworks_enabled" != 0 ]]; then
  export ASDF_DATA_DIR="${ASDF_DATA_DIR:-$HOME/.asdf}"
  export BUN_INSTALL="${BUN_INSTALL:-$HOME/.bun}"
fi
if [[ -z ${DOTFILES_BREW_PREFIX+x} ]] && (( $+commands[brew] )); then
  DOTFILES_BREW_PREFIX="$(brew --prefix 2>/dev/null)"
fi
typeset -a _dotfiles_paths
_dotfiles_paths=(
  "${DOTFILES_EXTRA_PATH[@]}"
)
[[ -n ${BUN_INSTALL:-} ]] && _dotfiles_paths+=("$BUN_INSTALL/bin")
[[ -n ${ASDF_DATA_DIR:-} ]] && _dotfiles_paths+=("$ASDF_DATA_DIR/shims")
if [[ -n ${DOTFILES_BREW_PREFIX:-} ]]; then
  _dotfiles_paths+=("$DOTFILES_BREW_PREFIX/bin" "$DOTFILES_BREW_PREFIX/opt/openjdk/bin")
fi
if (( ! ${+DOTFILES_USER_PATHS} )); then
  typeset -a DOTFILES_USER_PATHS=(
    "$HOME/bin" "$HOME/.local/bin" "$HOME/.yarn/bin"
    "${XDG_CONFIG_HOME:-$HOME/.config}/yarn/global/node_modules/.bin"
  )
fi
_dotfiles_paths+=("${DOTFILES_USER_PATHS[@]}")
for _dotfiles_path in "${(Oa)_dotfiles_paths[@]}"; do
  [[ -d "$_dotfiles_path" ]] && path=("$_dotfiles_path" $path)
done
unset _dotfiles_paths _dotfiles_path

# --- Oh My Zsh (optional) ---
if [[ "$_dotfiles_frameworks_enabled" != 0 ]] && (( ! $+functions[omz] )); then
  export ZSH="${ZSH:-$HOME/.oh-my-zsh}"
  ZSH_THEME="${ZSH_THEME-bira}"
  ZSH_DISABLE_COMPFIX="${ZSH_DISABLE_COMPFIX:-true}"
  DISABLE_AUTO_UPDATE="${DISABLE_AUTO_UPDATE:-true}"
  if [[ -z ${FZF_BASE:-} && -n ${DOTFILES_BREW_PREFIX:-} && -d "$DOTFILES_BREW_PREFIX/opt/fzf" ]]; then
    export FZF_BASE="$DOTFILES_BREW_PREFIX/opt/fzf"
  fi
  if (( ! ${+DOTFILES_ZSH_PLUGINS} )); then
    if (( ${+plugins} )); then
      typeset -a DOTFILES_ZSH_PLUGINS=("${plugins[@]}")
    else
      typeset -a DOTFILES_ZSH_PLUGINS=(git ssh-agent zsh-autosuggestions fzf)
    fi
  fi
  plugins=()
  for _dotfiles_plugin in "${DOTFILES_ZSH_PLUGINS[@]}"; do
    if [[ -f "${ZSH_CUSTOM:-$ZSH/custom}/plugins/$_dotfiles_plugin/$_dotfiles_plugin.plugin.zsh" ||
          -f "$ZSH/plugins/$_dotfiles_plugin/$_dotfiles_plugin.plugin.zsh" ]]; then
      plugins+=("$_dotfiles_plugin")
    fi
  done
  unset _dotfiles_plugin
  if (( ! ${+DOTFILES_SSH_IDENTITIES} )); then
    typeset -a DOTFILES_SSH_IDENTITIES=(id_ed25519)
  fi
  zstyle :omz:plugins:ssh-agent identities "${DOTFILES_SSH_IDENTITIES[@]}"
  [[ -r "$ZSH/oh-my-zsh.sh" ]] && source "$ZSH/oh-my-zsh.sh"
fi

# --- History and environment ---
HISTSIZE=10000
HISTFILE="${HISTFILE:-$HOME/.zsh_history}"
SAVEHIST=10000
setopt appendhistory sharehistory incappendhistory
export EDITOR="${EDITOR:-vi}"
export ZSH_AUTOSUGGEST_USE_ASYNC="${ZSH_AUTOSUGGEST_USE_ASYNC:-true}"
export PYTHON_BUILD_ARIA2_OPTS="${PYTHON_BUILD_ARIA2_OPTS:--x 10 -k 1M}"
# Inherit the machine's locale unless explicitly configured locally.
[[ -n ${DOTFILES_LOCALE:-} ]] && export LC_CTYPE="$DOTFILES_LOCALE"

# --- asdf ---
# Current asdf is an executable; only lazy-load scripts for legacy installs.
if [[ "$_dotfiles_frameworks_enabled" != 0 ]] && (( ! $+commands[asdf] && ! $+functions[asdf] )); then
  typeset _dotfiles_asdf_candidate
  for _dotfiles_asdf_candidate in \
    "${DOTFILES_ASDF_SCRIPT:-}" "${ASDF_DIR:-$HOME/.asdf}/asdf.sh" \
    "${DOTFILES_BREW_PREFIX:+$DOTFILES_BREW_PREFIX/opt/asdf/libexec/asdf.sh}"; do
    if [[ -n "$_dotfiles_asdf_candidate" && -r "$_dotfiles_asdf_candidate" ]]; then
      typeset _dotfiles_asdf_script="$_dotfiles_asdf_candidate"
      asdf() {
        unfunction asdf
        source "$_dotfiles_asdf_script" || return
        if (( $+functions[asdf] || $+commands[asdf] )); then
          asdf "$@"
        else
          print -u2 -- 'Legacy asdf initialization did not provide asdf.'
          return 127
        fi
      }
      break
    fi
  done
  unset _dotfiles_asdf_candidate
fi

# Use the shared helpers beside this file, including when this file is symlinked.
[[ -r "$_dotfiles_source_dir/.zshrc-functions" ]] && source "$_dotfiles_source_dir/.zshrc-functions"
unset _dotfiles_source_dir

# --- Alias tips ---
_alias_tips_preexec() {
  local cmd="${1%% *}" full="$1" best="" best_len=999 a e
  for a e in "${(@kv)aliases}"; do
    [[ "$full" == "$e" || "$full" == "$e "* ]] || continue
    (( ${#a} < best_len )) && best="$a" && best_len=${#a}
  done
  [[ -n "$best" && "$best" != "$cmd" ]] && \
    print -P "%F{blue}Alias tip: %B${best}%b%f"
}
autoload -Uz add-zsh-hook
add-zsh-hook preexec _alias_tips_preexec

# --- direnv (optional, resolved after PATH setup) ---
if [[ "$_dotfiles_frameworks_enabled" != 0 ]] && (( ! $+functions[_direnv_hook] )); then
  _direnv_bin="${commands[direnv]:-}"
  if [[ -n "$_direnv_bin" ]]; then
    _direnv_hook() {
      trap -- '' SIGINT
      eval "$("$_direnv_bin" export zsh)"
      trap - SIGINT
    }
    add-zsh-hook precmd _direnv_hook
  fi
fi

# --- Bun and editor (optional) ---
if [[ "$_dotfiles_frameworks_enabled" != 0 && -n ${BUN_INSTALL:-} && -r "$BUN_INSTALL/_bun" ]]; then
  source "$BUN_INSTALL/_bun"
fi
(( $+commands[nvim] )) && alias vim=nvim

# This final overlay may override any shared alias, function, or preference.
# An existing startup file owns its conventional overlay in coexistence mode.
if [[ -n ${DOTFILES_ZSH_LOCAL:-} && -r "$DOTFILES_ZSH_LOCAL" ]]; then
  source "$DOTFILES_ZSH_LOCAL"
elif [[ "$_dotfiles_frameworks_enabled" != 0 && -z ${DOTFILES_ZSH_LOCAL:-} && -r "$HOME/.zshrc-local" ]]; then
  source "$HOME/.zshrc-local"
fi
unset _dotfiles_frameworks_enabled
