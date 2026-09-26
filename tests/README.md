# Verification

Run the standard-library test suite from the checkout:

```sh
python3 -B -m unittest discover -s tests -v
```

The tests create temporary destinations and use explicit configuration overrides.
They do not replace the real home directory or run the installer against it.
Tool-dependent checks report when a required executable is unavailable.

Before sharing current files, run:

```sh
python3 scripts/check-public.py
```

That check requires Gitleaks. A successful current-file check does not remove
sensitive historical commits; outgoing-history checks intentionally examine them.

The full Neovim integration test also needs an **isolated** plugin fixture
populated at the revisions in `.config/nvim/lazy-lock.json`:

```sh
DOTFILES_NVIM_TEST_PLUGIN_ROOT=/path/to/isolated/lazy \
  python3 -B -m unittest discover -s tests -v
```

Never point this variable at your live Neovim plugin directory. Tests copy the
configuration and redirect XDG config/data/state/cache paths to temporary
locations; automatic plugin/tool installation is disabled during tests.
Native parser/FZF builds and real language-server processes need their own
platform-specific integration checks. A passing macOS suite does not certify
native Linux, WSL, or Windows behavior.
