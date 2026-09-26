#!/usr/bin/env python3
"""Install an explicit set of shared links and private writable configuration."""

import argparse
import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


REPO = Path(__file__).resolve().parent.parent


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
        self.manifest = read_object(REPO / "install-manifest.json")
        if self.manifest.get("version") != 1:
            raise ValueError("Unsupported install manifest version")
        self.entries = []
        destinations = set()
        for kind in ("links", "seeds"):
            for item in self.manifest[kind]:
                source = REPO / relative_path(item["source"])
                roots = {"home": self.home, "config": self.config}
                if item["root"] not in roots:
                    raise ValueError("Unknown destination root")
                destination = roots[item["root"]] / relative_path(item["target"])
                physical = outside_repository(destination, "Configuration destination", follow_leaf=False)
                if physical in destinations:
                    raise ValueError("Duplicate installation destination")
                destinations.add(physical)
                if not source.is_file() or not source.resolve().is_relative_to(REPO):
                    raise ValueError("Missing or external manifest source: " + item["source"])
                if destination.is_dir() and not destination.is_symlink():
                    raise ValueError("Refusing to replace a directory: " + str(destination))
                if kind == "seeds" and destination.is_symlink() and not destination.exists():
                    raise ValueError("Broken configuration link: " + str(destination) +
                                     "; restore its local contents before installing")
                if kind == "seeds" and destination.exists() and not destination.is_file():
                    raise ValueError("Expected a regular configuration file: " + str(destination))
                if kind == "seeds" and destination.is_file():
                    # Verify readability now, before any earlier links change.
                    with destination.open("rb"):
                        pass
                self.entries.append((kind, source, destination))
        # Validate all optional input before modifying any destination.
        self.flipper_data = None
        if args.render_flipper or args.flipper_overrides:
            self.flipper_data = self.prepare_flipper()
        self.auto_sync = True if args.enable_auto_sync else False if args.disable_auto_sync else None
        self.auto_sync_before = self.read_auto_sync() if self.auto_sync is not None else None
        self.hook_entries = self.prepare_hooks() if args.install_hooks or args.enable_auto_sync else []

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
            if kind == "links":
                self.install_link(source, destination)
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
    parser.add_argument("--dry-run", action="store_true", help="preview without writing files")
    parser.add_argument("--target-dir", default=os.environ.get("DOTFILES_TARGET_DIR", str(Path.home())))
    parser.add_argument("--config-dir", default=os.environ.get("DOTFILES_CONFIG_DIR"), help="XDG configuration destination")
    parser.add_argument("--local-dir", default=os.environ.get("DOTFILES_LOCAL_DIR"), help="private overrides directory")
    parser.add_argument("--render-flipper", action="store_true", help="merge defaults, existing local settings and private overrides")
    parser.add_argument("--flipper-overrides", help="private JSON override object; also enables rendering")
    parser.add_argument("--install-hooks", action="store_true", help="install optional pre-commit/pre-push checks with backups")
    sync = parser.add_mutually_exclusive_group()
    sync.add_argument("--enable-auto-sync", action="store_true",
                      help="install privacy hooks and opt this clone into pushing deliberate commits")
    sync.add_argument("--disable-auto-sync", action="store_true",
                      help="turn off this clone's auto-push setting without removing hooks")
    args = parser.parse_args()
    try:
        Installer(args).run()
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        print("Install failed:", error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
