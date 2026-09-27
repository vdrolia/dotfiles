#!/usr/bin/env python3
"""Compose selected dotfile modules with existing configuration safely."""

import argparse
import datetime
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile


REPO = Path(__file__).resolve().parent.parent
COMPONENTS = ("zsh", "git", "vim", "tmux", "nvim", "ack", "tools", "htop", "flipper")
PROFILE_MARKER = ".dotfiles-managed-profile.json"
LAUNCHER_HEADER = b"#!/bin/sh\n# Managed dotfiles Neovim launcher.\n"


def quoted_path(path, syntax):
    value = str(path)
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError("Configuration paths must not contain control characters")
    if syntax == "zsh":
        return shlex.quote(value)
    if syntax == "vim":
        return "'" + value.replace("'", "''") + "'"
    if syntax == "tmux":
        # source-file glob-expands after parsing its quoted argument. Preserve
        # literal path metacharacters through both interpretation stages.
        value = "".join("\\" + character if character in "\\*?[]" else character for character in value)
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    if syntax == "tmux":
        escaped = escaped.replace("$", "\\$").replace("`", "\\`")
    return '"' + escaped + '"'


def source_line(path, syntax):
    quoted = quoted_path(path, syntax)
    if syntax == "git":
        return "[include]\n  path = " + quoted + "\n"
    if syntax == "vim":
        return "execute 'source ' . fnameescape(" + quoted + ")\n"
    return ("source-file " if syntax == "tmux" else "source ") + quoted + "\n"


def managed_body(data, component):
    comment = '"' if component == "vim" else "#"
    start = (comment + " >>> dotfiles managed " + component + " >>>\n").encode()
    end = (comment + " <<< dotfiles managed " + component + " <<<\n").encode()
    if start not in data and end not in data:
        return data, start, end
    if not data.startswith(start) or data.count(start) != 1 or data.count(end) != 1:
        raise ValueError("Malformed or moved managed block; integrate this configuration manually")
    position = data.index(end)
    return data[position + len(end):], start, end


def read_object(path):
    with path.open(encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object in " + str(path))
    return value


def merge_objects(base, overrides):
    result = dict(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge_objects(result[key], value)
        else:
            result[key] = value
    return result


def relative_path(value):
    path = Path(value)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise ValueError("Manifest paths must be nonempty relative paths without '..'")
    return path


def xdg_directory(name):
    value = os.environ.get(name)
    if not value:
        return None
    directory = Path(value)
    if not directory.is_absolute():
        raise ValueError(name + " must be an absolute path")
    return directory


def outside_repository(path, description, follow_leaf=True):
    # Replacing a leaf symlink is safe; following a parent symlink into the
    # checkout would replace the shared source itself. Private directories
    # follow their final component too, since files are created inside them.
    try:
        physical = path.resolve() if follow_leaf else path.parent.resolve() / path.name
    except (OSError, RuntimeError) as error:
        raise ValueError("Cannot resolve " + description + ": " + str(path)) from error
    if physical.is_relative_to(REPO):
        raise ValueError(description + " must be outside the repository: " + str(path))
    return physical


class Installer:
    def __init__(self, args):
        self.args = args
        self.selected = set(COMPONENTS if args.components == "all" else
                            [] if args.components == "none" else args.components.split(","))
        if not self.selected <= set(COMPONENTS):
            raise ValueError("Unknown component; use --list-components")
        self.home = Path(args.target_dir).expanduser().absolute()
        actual_home = self.home.resolve() == Path.home().resolve()
        config_default = xdg_directory("XDG_CONFIG_HOME") if actual_home and not args.config_dir else None
        self.config = Path(args.config_dir or config_default or self.home / ".config").expanduser().absolute()
        self.local = Path(args.local_dir or self.config / "dotfiles").expanduser().absolute()
        state_default = xdg_directory("XDG_STATE_HOME") if actual_home else None
        state = Path(state_default or self.home / ".local/state").expanduser().absolute()
        self.backup_root = state / "dotfiles/backups"
        for directory, description in (
                (self.home, "Installation home"),
                (self.config, "Configuration directory"),
                (self.local, "Private overrides directory"),
                (self.backup_root, "Private backup directory")):
            outside_repository(directory, description)
        self.backup_dir = None
        self.records = []
        self.checked_parents = {}
        self.validate_destination(self.backup_root / "manifest.json")
        self.manifest = read_object(REPO / "install-manifest.json")
        if self.manifest.get("version") != 2:
            raise ValueError("Unsupported install manifest version")
        self.zsh = Path(args.zsh_dir or (os.environ.get("ZDOTDIR") if actual_home else None) or self.home).expanduser().absolute()
        self.entrypoints = {
            "zsh": self.zsh / ".zshrc",
            "git": self.native_entrypoint(args.git_config or (os.environ.get("GIT_CONFIG_GLOBAL") if actual_home else None),
                                          [self.config / "git/config", self.home / ".gitconfig"], self.home / ".gitconfig"),
            "vim": self.native_entrypoint(args.vim_config, [self.home / ".vimrc", self.home / ".vim/vimrc"], self.home / ".vimrc"),
            "tmux": self.native_entrypoint(args.tmux_config, [self.home / ".tmux.conf", self.config / "tmux/tmux.conf"], self.home / ".tmux.conf"),
        }
        self.entries = []
        self.profile = None
        self.profile_source = REPO
        if "nvim" in self.selected and args.mode == "modular":
            self.prepare_profile()
        destinations = set()
        for kind in ("links", "seeds"):
            for item in self.manifest[kind]:
                component = item["component"]
                if component not in COMPONENTS:
                    raise ValueError("Unknown manifest component")
                if component not in self.selected:
                    continue
                if args.mode == "modular" and component == "zsh" and item["target"] == ".zshrc-functions":
                    continue
                source = REPO / relative_path(item["source"])
                roots = {"home": self.home, "config": self.config}
                if item["root"] not in roots:
                    raise ValueError("Unknown destination root")
                destination = roots[item["root"]] / relative_path(item["target"])
                action = kind
                if component in self.entrypoints and item["target"] != ".zshrc-functions":
                    destination = self.entrypoints[component]
                    if args.mode == "modular" or component == "git":
                        action = "include"
                elif component == "nvim" and self.profile is not None:
                    destination = self.profile / relative_path(item["target"]).relative_to("nvim")
                    action = "profile-seed" if destination.name == "lazy-lock.json" else "profile-link"
                elif component == "ack" and args.mode == "modular":
                    action = "preserve-seed"
                elif kind == "seeds" and args.mode == "modular":
                    action = "preserve-seed"
                physical = self.validate_destination(destination)
                if physical in destinations:
                    raise ValueError("Duplicate installation destination")
                destinations.add(physical)
                if not source.is_file() or not source.resolve().is_relative_to(REPO):
                    raise ValueError("Missing or external manifest source: " + item["source"])
                if action == "preserve-seed" and (destination.exists() or destination.is_symlink()):
                    self.entries.append(("preserve", source, destination))
                    continue
                if destination.is_dir() and not destination.is_symlink():
                    raise ValueError("Refusing to replace a directory: " + str(destination))
                if action in {"seeds", "include", "profile-seed", "profile-link"} and destination.is_symlink() and not destination.exists():
                    old_source = self.profile_source / relative_path(item["source"])
                    if action != "profile-link" or destination.resolve() not in {source.resolve(), old_source.resolve()}:
                        raise ValueError("Broken configuration link: " + str(destination) +
                                         "; restore its local contents before installing")
                if destination.exists() and not destination.is_file():
                    raise ValueError("Expected a regular configuration file: " + str(destination))
                if action == "include":
                    self.entries.append(("write", self.prepare_include(component, source, destination), destination))
                    continue
                if action in {"profile-link", "profile-seed"} and destination.exists():
                    old_source = self.profile_source / relative_path(item["source"])
                    if destination.is_symlink():
                        if destination.resolve() not in {source.resolve(), old_source.resolve()}:
                            raise ValueError("Unrelated file in managed Neovim profile; preserve it and select another --nvim-profile")
                    elif action == "profile-link":
                        raise ValueError("Locally edited file in managed Neovim profile; integrate it manually")
                if action in {"seeds", "profile-seed"} and destination.is_file():
                    # Verify readability now, before any earlier links change.
                    with destination.open("rb"):
                        pass
                self.entries.append((action, source, destination))
        if self.profile is not None:
            self.finish_profile()
        # Validate all optional input before modifying any destination.
        self.flipper_data = None
        if args.render_flipper or args.flipper_overrides:
            if "flipper" not in self.selected:
                raise ValueError("Flipper rendering requires the flipper component")
            self.flipper_data = self.prepare_flipper()
        self.auto_sync = True if args.enable_auto_sync else False if args.disable_auto_sync else None
        self.auto_sync_before = self.read_auto_sync() if self.auto_sync is not None else None
        self.hook_entries = self.prepare_hooks() if args.install_hooks or args.enable_auto_sync else []

    def native_entrypoint(self, configured, candidates, fallback):
        if configured:
            return Path(configured).expanduser().absolute()
        return next((path for path in candidates if path.exists() or path.is_symlink()), fallback)

    def validate_destination(self, destination):
        physical = outside_repository(destination, "Configuration destination", follow_leaf=False)
        parent = physical.parent
        if parent not in self.checked_parents:
            nearest = parent
            while not nearest.exists() and nearest != nearest.parent:
                nearest = nearest.parent
            if not nearest.is_dir():
                raise ValueError("Configuration parent must be a directory: " + str(nearest))
            env = {key: value for key, value in os.environ.items() if key not in {
                "GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE", "GIT_PREFIX",
                "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
            }}
            env["GIT_OPTIONAL_LOCKS"] = "0"
            result = subprocess.run(["git", "-C", str(nearest), "rev-parse", "--show-toplevel"],
                                    capture_output=True, text=True, env=env)
            self.checked_parents[parent] = result.returncode == 0
        if self.checked_parents[parent]:
            raise ValueError("Destination parent is inside a Git checkout; use manual includes instead: " + str(destination))
        return physical

    def prepare_include(self, component, source, destination):
        owned_link = destination.is_symlink() and destination.resolve() == source.resolve()
        if destination.is_symlink() and not owned_link:
            body = source_line(destination.resolve(), component).encode()
        elif owned_link or not destination.exists():
            body = b""
        else:
            body = destination.read_bytes()
            if b"\0" in body or body.startswith((b"\xef\xbb\xbf", b"\xff\xfe", b"\xfe\xff")):
                raise ValueError("Configuration has a byte-order mark or binary data; add a native include manually")
        previous = body
        body, start, end = managed_body(body, component)
        comment = '"' if component == "vim" else "#"
        mode_prefix = (comment + " dotfiles load mode: ").encode()
        modes = ([line[len(mode_prefix):] for line in previous[:previous.index(end)].splitlines()
                  if line.startswith(mode_prefix)] if previous.startswith(start) else [])
        if modes and (len(modes) != 1 or modes[0] not in {b"standalone", b"coexist"}):
            raise ValueError("Invalid managed load mode; integrate this configuration manually")
        coexist = modes[0] == b"coexist" if modes else bool(body.strip())
        include = source_line(source, component)
        if component == "zsh":
            include = ('[[ -n "${DOTFILES_LOCAL_DIR:-}" ]] || export DOTFILES_LOCAL_DIR=' +
                       quoted_path(self.local, "zsh") + "\n" +
                       ("DOTFILES_ZSH_FRAMEWORKS=0 " if coexist else "") + include)
        elif component == "vim" and coexist:
            include = (
                "let s:dotfiles_had_coexist = exists('g:dotfiles_coexist')\n"
                "let s:dotfiles_saved_coexist = get(g:, 'dotfiles_coexist', 0)\n"
                "let g:dotfiles_coexist = 1\ntry\n  " + include +
                "finally\n  if s:dotfiles_had_coexist\n"
                "    let g:dotfiles_coexist = s:dotfiles_saved_coexist\n"
                "  else\n    unlet! g:dotfiles_coexist\n  endif\n"
                "  unlet s:dotfiles_had_coexist s:dotfiles_saved_coexist\nendtry\n")
        elif component == "tmux" and coexist:
            include = (
                'set -gF @dotfiles_loader_previous_coexist "#{@dotfiles_coexist}"\n'
                "set -g @dotfiles_coexist 1\n" + include +
                'if-shell -F "#{==:#{@dotfiles_loader_previous_coexist},}" '
                "'set -gu @dotfiles_coexist' "
                "'set -gF @dotfiles_coexist \"#{@dotfiles_loader_previous_coexist}\"'\n"
                "set -gu @dotfiles_loader_previous_coexist\n")
        elif component == "git" and not coexist:
            include += source_line(self.home / ".gitconfig.local", "git")
        mode = mode_prefix + (b"coexist" if coexist else b"standalone") + b"\n"
        return start + mode + include.encode() + end + body

    def prepare_profile(self):
        name = self.args.nvim_profile
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name) or name in {"nvim", ".", ".."}:
            raise ValueError("--nvim-profile must be a single safe directory name other than nvim")
        self.profile = self.config / name
        self.validate_destination(self.profile / PROFILE_MARKER)
        if self.profile.is_symlink():
            raise ValueError("Neovim profile directory must not be a symlink; select another --nvim-profile")
        if self.profile.exists():
            marker = self.profile / PROFILE_MARKER
            if not self.profile.is_dir() or not marker.is_file() or marker.is_symlink():
                raise ValueError("Existing Neovim profile is unrelated; select another --nvim-profile")
            metadata = read_object(marker)
            if metadata.get("format") != 1 or not isinstance(metadata.get("source"), str):
                raise ValueError("Invalid Neovim ownership marker; integrate this profile manually")
            self.profile_source = Path(metadata["source"])
            if not self.profile_source.is_absolute():
                raise ValueError("Invalid Neovim ownership marker source")

    def finish_profile(self):
        marker = (json.dumps({"format": 1, "source": str(REPO)}, indent=2) + "\n").encode()
        self.entries.append(("write", marker, self.profile / PROFILE_MARKER))
        launcher = self.home / ".local/bin" / self.args.nvim_profile
        self.validate_destination(launcher)
        if launcher.exists() or launcher.is_symlink():
            if (launcher.is_symlink() or not launcher.is_file() or
                    not launcher.read_bytes().startswith(LAUNCHER_HEADER)):
                raise ValueError("Existing dotfiles-nvim launcher is unrelated; integrate it manually")
        script = ("export NVIM_APPNAME=" + quoted_path(self.args.nvim_profile, "zsh") + "\n" +
                  "export XDG_CONFIG_HOME=" + quoted_path(self.config, "zsh") + "\n" +
                  '[ -n "${DOTFILES_LOCAL_DIR:-}" ] || DOTFILES_LOCAL_DIR=' + quoted_path(self.local, "zsh") + "\n" +
                  "export DOTFILES_LOCAL_DIR\nexec nvim \"$@\"\n")
        self.entries.append(("executable", LAUNCHER_HEADER + script.encode(), launcher))

    def backup(self, destination):
        if not destination.exists() and not destination.is_symlink():
            return
        if self.backup_dir is None:
            self.backup_root.mkdir(parents=True, exist_ok=True, mode=0o700)
            stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-")
            self.backup_dir = Path(tempfile.mkdtemp(prefix=stamp, dir=self.backup_root))
        entry = {"destination": str(destination)}
        if destination.is_symlink():
            entry["symlink"] = os.readlink(destination)
        if destination.is_file():
            name = str(len(self.records)) + "-" + destination.name
            saved = self.backup_dir / name
            shutil.copy2(destination, saved)
            saved.chmod(0o600)
            entry["contents"] = name
        self.records.append(entry)
        path = self.backup_dir / "manifest.json"
        path.write_text(json.dumps(self.records, indent=2) + "\n", encoding="utf-8")
        path.chmod(0o600)

    def write_file(self, destination, data, mode=0o600):
        if (destination.is_file() and not destination.is_symlink()
                and destination.read_bytes() == data
                and destination.stat().st_mode & 0o777 == mode):
            print("Keep", destination)
            return
        print("Write", destination)
        if self.args.dry_run:
            return
        self.backup(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix="." + destination.name + ".", dir=destination.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
            os.chmod(temporary, mode)
            os.replace(temporary, destination)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def install_link(self, source, destination):
        if destination.is_symlink() and destination.resolve() == source.resolve():
            print("Keep", destination)
            return
        print("Link", destination, "->", source)
        if self.args.dry_run:
            return
        self.backup(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix="." + destination.name + ".", dir=destination.parent)
        os.close(fd)
        os.unlink(temporary)
        try:
            os.symlink(source, temporary)
            os.replace(temporary, destination)
        finally:
            if os.path.lexists(temporary):
                os.unlink(temporary)

    def install_seed(self, source, destination):
        if destination.is_symlink():
            # Detach app-owned files while preserving their current contents.
            self.write_file(destination, destination.read_bytes())
        elif destination.exists():
            print("Keep local", destination)
        else:
            self.write_file(destination, source.read_bytes())

    def prepare_flipper(self):
        target = self.config / "flipper/settings.json"
        outside_repository(target, "Flipper output", follow_leaf=False)
        data = read_object(REPO / "templates/flipper/settings.json")
        if target.exists():
            data = merge_objects(data, read_object(target))
        override = Path(self.args.flipper_overrides).expanduser() if self.args.flipper_overrides else self.local / "flipper.json"
        if self.args.flipper_overrides and not override.is_file():
            raise ValueError("Flipper override does not exist: " + str(override))
        if override.exists():
            data = merge_objects(data, read_object(override))
        return (json.dumps(data, indent=2) + "\n").encode()

    def prepare_hooks(self):
        env = dict(os.environ, GIT_OPTIONAL_LOCKS="0")
        configured = subprocess.run(["git", "-C", str(REPO), "config", "--get", "core.hooksPath"],
                                    capture_output=True, text=True, env=env)
        if configured.returncode == 0:
            raise ValueError("A custom core.hooksPath is configured; integrate the optional hooks there explicitly")
        result = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--git-path", "hooks"],
                                capture_output=True, text=True, check=True, env=env)
        directory = Path(result.stdout.strip())
        if not directory.is_absolute():
            directory = REPO / directory
        entries = []
        names = ["pre-commit", "pre-push"]
        if self.args.enable_auto_sync:
            names.append("post-commit")
        for name in names:
            target = directory / name
            if target.is_dir():
                raise ValueError("Refusing to replace a hooks directory")
            entries.append((target, (REPO / ".githooks" / name).read_bytes()))
        return entries

    def read_auto_sync(self):
        result = subprocess.run(["git", "-C", str(REPO), "config", "--local", "--get-all", "dotfiles.autoSync"],
                                capture_output=True, text=True, env=dict(os.environ, GIT_OPTIONAL_LOCKS="0"))
        if result.returncode not in (0, 1):
            raise ValueError("Cannot read clone-local auto-sync configuration; no files changed")
        return result.stdout.splitlines()

    def configure_auto_sync(self):
        if self.auto_sync is None:
            return
        value = "true" if self.auto_sync else "false"
        if self.auto_sync_before == [value]:
            print("Keep clone-local auto-sync", value)
            return
        print("Set clone-local auto-sync", value)
        if not self.args.dry_run:
            subprocess.run(["git", "-C", str(REPO), "config", "--local", "--replace-all",
                            "dotfiles.autoSync", value], check=True,
                           env=dict(os.environ, GIT_OPTIONAL_LOCKS="0"))

    def run(self):
        for kind, source, destination in self.entries:
            if kind in {"links", "profile-link"}:
                self.install_link(source, destination)
            elif kind == "write":
                self.write_file(destination, source)
            elif kind == "executable":
                self.write_file(destination, source, 0o755)
            elif kind == "preserve":
                print("Keep existing", destination)
            else:
                self.install_seed(source, destination)
        if self.flipper_data is not None:
            self.write_file(self.config / "flipper/settings.json", self.flipper_data)
        for target, data in self.hook_entries:
            self.write_file(target, data, 0o755)
        # Enable only after every required hook has been installed successfully.
        self.configure_auto_sync()
        if self.backup_dir:
            print("Private backups:", self.backup_dir)
        if self.args.dry_run:
            print("Preview only; no files changed.")


def main():
    if sys.version_info < (3, 9):
        print("Python 3.9+ is required.", file=sys.stderr)
        return 1
    if os.name == "nt":
        print("Use WSL for installation; native Windows is not supported.", file=sys.stderr)
        return 1
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("modular", "link"), default="modular",
                        help="compose with existing files (default), or explicitly replace with links")
    parser.add_argument("--components", default="all", help="comma-separated components, all, or none")
    parser.add_argument("--list-components", action="store_true", help="list supported components and exit")
    parser.add_argument("--dry-run", action="store_true", help="preview without writing files")
    parser.add_argument("--target-dir", default=os.environ.get("DOTFILES_TARGET_DIR", str(Path.home())))
    parser.add_argument("--config-dir", default=os.environ.get("DOTFILES_CONFIG_DIR"), help="XDG configuration destination")
    parser.add_argument("--local-dir", default=os.environ.get("DOTFILES_LOCAL_DIR"), help="private overrides directory")
    parser.add_argument("--zsh-dir", help="directory containing .zshrc (defaults to ZDOTDIR for the real home)")
    parser.add_argument("--git-config", help="explicit Git global configuration entrypoint")
    parser.add_argument("--vim-config", help="explicit Vim configuration entrypoint")
    parser.add_argument("--tmux-config", help="explicit tmux configuration entrypoint")
    parser.add_argument("--nvim-profile", default="dotfiles-nvim", help="isolated Neovim profile name in modular mode")
    parser.add_argument("--render-flipper", action="store_true", help="merge defaults, existing local settings and private overrides")
    parser.add_argument("--flipper-overrides", help="private JSON override object; also enables rendering")
    parser.add_argument("--install-hooks", action="store_true", help="install optional pre-commit/pre-push checks with backups")
    sync = parser.add_mutually_exclusive_group()
    sync.add_argument("--enable-auto-sync", action="store_true",
                      help="install privacy hooks and opt this clone into pushing deliberate commits")
    sync.add_argument("--disable-auto-sync", action="store_true",
                      help="turn off this clone's auto-push setting without removing hooks")
    args = parser.parse_args()
    if args.list_components:
        print("\n".join(COMPONENTS))
        return 0
    try:
        Installer(args).run()
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        print("Install failed:", error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
