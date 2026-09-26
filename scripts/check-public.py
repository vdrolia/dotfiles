#!/usr/bin/env python3
"""Check candidate public files, the exact index, or all outgoing commit trees.

Credentials are checked with mandatory gitleaks defaults. A private UTF-8 file
selected by DOTFILES_PRIVACY_DENYLIST supplies case-insensitive literal strings,
one per line (blank lines and lines starting with # are ignored). Otherwise an
existing privacy-denylist.txt in DOTFILES_LOCAL_DIR, or the XDG configuration
directory's dotfiles folder, is used. Keep it outside this repository. Findings
never echo matched text or scanner output.
"""
import argparse
import ipaddress
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile


EMAIL = re.compile(r"(?<![\w.+-])[\w.+-]+@(?:[\w-]+\.)+[A-Za-z]{2,}(?![\w.-])")
HOME_PATH = re.compile(r"(?<![\w])/(?:Users|home)/[A-Za-z0-9_.-]+")
IPV4 = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])")
IPV6 = re.compile(r"(?i)(?<![\da-f:])(?:f[cd][\da-f]{2}|fe[89ab][\da-f]):[\da-f:]+")
OID = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")


class CheckError(Exception):
    """A safe, non-sensitive explanation of why checking could not complete."""


def git(*args):
    result = subprocess.run(["git", "--no-lazy-fetch", *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            env=dict(os.environ, GIT_OPTIONAL_LOCKS="0", GIT_NO_REPLACE_OBJECTS="1"))
    if result.returncode:
        raise CheckError("Git could not read the requested snapshot; no publication approved.")
    return result.stdout


def denylist():
    configured = os.environ.get("DOTFILES_PRIVACY_DENYLIST")
    if not configured:
        local_dir = os.environ.get("DOTFILES_LOCAL_DIR")
        if local_dir:
            directory = Path(local_dir).expanduser()
        else:
            config_dir = os.environ.get("XDG_CONFIG_HOME")
            directory = (Path(config_dir).expanduser() if config_dir else Path.home() / ".config") / "dotfiles"
        default = directory / "privacy-denylist.txt"
        if not default.exists() and not default.is_symlink():
            return []
        configured = str(default)
    try:
        path = Path(configured).expanduser().resolve()
        checkout = Path.cwd().resolve()
        if path == checkout or checkout in path.parents:
            raise CheckError("The private denylist must resolve outside this checkout.")
        values = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError, RuntimeError):
        raise CheckError("The configured private denylist could not be read.") from None
    return [line.strip().casefold() for line in values if line.strip() and not line.lstrip().startswith("#")]


def text_reasons(text, private_terms):
    reasons = set()
    for match in EMAIL.finditer(text):
        user, domain = match.group().rsplit("@", 1)
        domain = domain.lower()
        public_git_url = (user == "git" and domain in {"github.com", "gitlab.com", "bitbucket.org"}
                          and (text[match.end():match.end() + 1] == ":" or
                               text[max(0, match.start() - 6):match.start()] == "ssh://"))
        if public_git_url:
            continue
        if domain not in {"example.com", "example.net", "example.org"} and not domain.endswith(".invalid"):
            reasons.add("email address")
    if HOME_PATH.search(text):
        reasons.add("personal home path")
    for match in IPV4.finditer(text):
        try:
            octets = list(ipaddress.IPv4Address(match.group()).packed)
        except ipaddress.AddressValueError:
            continue
        if (octets[0] == 10 or octets[:2] == [192, 168] or
                (octets[0] == 172 and 16 <= octets[1] <= 31) or
                (octets[0] == 100 and 64 <= octets[1] <= 127) or octets[:2] == [169, 254]):
            reasons.add("private IP address")
    for match in IPV6.finditer(text):
        try:
            address = ipaddress.IPv6Address(match.group())
        except ipaddress.AddressValueError:
            continue
        if address.is_private or address.is_link_local:
            reasons.add("private IP address")
    folded = text.casefold()
    if any(term in folded for term in private_terms):
        reasons.add("private denylist match")
    return reasons


def prohibited(path):
    parts = PurePosixPath(path).parts
    private_dirs = {".claude", ".ssh", ".aws", ".kube", ".gnupg", ".codex"}
    if any(part in private_dirs for part in parts) or (parts and parts[0] in {"claude", "private", "local"}):
        return True
    if parts[:2] == (".config", "dotfiles") or path in {
            ".config/nvim/local.lua", ".config/nvim/lua/config/local.lua"}:
        return True
    name = parts[-1] if parts else ""
    return (name.startswith(".claude.json") or name in {
        ".gitconfig.local", ".zshrc-local", ".vimrc.local", ".tmux.conf.local",
        "settings.local.json",
        "credentials.json", "credentials", "id_rsa", "id_ed25519", ".netrc",
        ".npmrc", ".pypirc", ".python_history", ".zsh_history", ".bash_history",
        "privacy-denylist", "privacy-denylist.txt",
    } or (name.startswith(".env") and name not in {".env.example", ".env.sample"}))


def working_files():
    paths = git("ls-files", "-z", "--cached", "--others", "--exclude-standard").split(b"\0")
    for raw in sorted(set(paths)):
        if not raw:
            continue
        name = os.fsdecode(raw)
        path = Path(name)
        if path.is_symlink():
            yield name, os.fsencode(os.readlink(path))
        elif path.is_file():
            yield name, path.read_bytes()
        elif path.exists():
            raise CheckError("A candidate path is not a regular file; review submodules separately.")
        # Unstaged deletions are deliberately absent from the working-tree export.


def staged_files():
    for record in git("ls-files", "--stage", "-z").split(b"\0"):
        if not record:
            continue
        info, raw_path = record.split(b"\t", 1)
        mode, oid, stage = info.decode("ascii").split()
        if stage != "0":
            raise CheckError("The index has unresolved conflicts.")
        if mode == "160000":
            raise CheckError("The index includes a submodule; review its contents separately.")
        yield os.fsdecode(raw_path), git("cat-file", "blob", oid)


def push_files(updates):
    if git("rev-parse", "--is-shallow-repository").strip() != b"false":
        raise CheckError("Outgoing history cannot be verified in a shallow checkout.")
    grafts = Path(os.fsdecode(git("rev-parse", "--git-path", "info/grafts").strip()))
    if grafts.exists() and grafts.stat().st_size:
        raise CheckError("Legacy Git grafts can hide outgoing history; manual review required.")
    commits = set()
    tag_objects = set()
    for line in updates.splitlines():
        fields = line.split()
        if len(fields) != 4 or not OID.fullmatch(fields[1]) or not OID.fullmatch(fields[3]):
            raise CheckError("Malformed pre-push input; no publication approved.")
        _, local, remote_ref, remote = fields
        if set(local) == {"0"}:
            continue
        yield "<outgoing ref name>", remote_ref.encode("utf-8")
        kind = git("cat-file", "-t", local).strip()
        peeled = local
        # Include annotated tag text, even for nested tags and already-shared commits.
        while kind == b"tag":
            tag_objects.add(peeled)
            raw = git("cat-file", "tag", peeled)
            peeled = raw.splitlines()[0].split()[1].decode("ascii")
            kind = git("cat-file", "-t", peeled).strip()
        if kind != b"commit":
            raise CheckError("An outgoing ref does not point to commits; manual review required.")
        args = ["rev-list", peeled]
        if set(remote) != {"0"}:
            # Missing remote objects fail closed instead of silently narrowing the scan.
            args += ["--not", remote]
        commits.update(git(*args).decode("ascii").splitlines())
    for oid in sorted(tag_objects):
        yield "<tag metadata " + oid[:12] + ">", git("cat-file", "tag", oid)
    seen = set()
    for commit in sorted(commits):
        yield "<commit metadata " + commit[:12] + ">", git("cat-file", "commit", commit)
        for record in git("ls-tree", "-r", "-z", commit).split(b"\0"):
            if not record:
                continue
            info, raw_path = record.split(b"\t", 1)
            mode, kind, oid = info.decode("ascii").split()
            if kind != "blob" or mode == "160000":
                raise CheckError("Outgoing history contains a submodule; manual review required.")
            key = (raw_path, oid)
            if key not in seen:
                seen.add(key)
                yield os.fsdecode(raw_path), git("cat-file", "blob", oid)


def check(files, private_terms):
    scanner = shutil.which("gitleaks")
    if not scanner:
        raise CheckError("Required gitleaks scanner is unavailable; install it before publication.")
    findings = []
    count = 0
    hide_filenames = False
    with tempfile.TemporaryDirectory(prefix="dotfiles-public-check-") as directory:
        root = Path(directory)
        exported = root / "export"
        exported.mkdir(mode=0o700)
        config = root / "scanner.toml"
        config.write_text("[extend]\nuseDefault = true\n", encoding="utf-8")
        ignore = root / "empty.ignore"
        ignore.touch(mode=0o600)
        filenames = []
        for count, (name, data) in enumerate(files, 1):
            filenames.append(name)
            filename_reasons = text_reasons(name, private_terms)
            if prohibited(name):
                filename_reasons.add("prohibited private path")
            # Suppress sensitive filenames, control characters, and terminal escapes.
            safe_name = name if not filename_reasons and name.isprintable() else "<sensitive filename>"
            findings.extend((safe_name, 0, reason) for reason in sorted(filename_reasons))
            if b"\0" in data:
                findings.append((safe_name, 0, "binary file requires manual privacy review"))
            if data.startswith(b"version https://git-lfs.github.com/spec/v1\n"):
                findings.append((safe_name, 0, "Git LFS payload requires a separate privacy review"))
            for number, line in enumerate(data.decode("utf-8", errors="replace").splitlines(), 1):
                findings.extend((safe_name, number, reason) for reason in sorted(text_reasons(line, private_terms)))
            # Preserve filenames for path-sensitive credential rules. Each snapshot
            # gets its own directory, with no symlinks or repository-supplied rules.
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts:
                raise CheckError("Unsafe candidate filename; no publication approved.")
            destination = exported / str(count) / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
        (exported / "filenames.txt").write_text("\n".join(filenames), encoding="utf-8", errors="replace")
        env = {key: value for key, value in os.environ.items()
               if key not in {"GITLEAKS_CONFIG", "GITLEAKS_CONFIG_TOML"}}
        scan = subprocess.run([scanner, "dir", "--no-banner", "--no-color", "--redact",
                               "--ignore-gitleaks-allow", "--config", str(config),
                               "--gitleaks-ignore-path", str(ignore),
                               "--max-archive-depth", "2", str(exported)],
                              cwd=root, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if scan.returncode == 1:
            # A credential can itself be a filename, so hide every path whenever
            # the credential scanner reports a match anywhere in this snapshot.
            hide_filenames = True
            findings.append(("<credential scan>", 0, "credential detected; scanner output suppressed"))
        elif scan.returncode != 0:
            raise CheckError("gitleaks could not complete; scanner output suppressed.")
    for name, number, reason in findings[:100]:
        location = ("<redacted path>" if hide_filenames else name) + (":" + str(number) if number else "")
        print("BLOCKED: " + location + ": " + reason)
    if len(findings) > 100:
        print("Additional findings suppressed:", len(findings) - 100)
    if findings:
        print("Public check failed; matched values are intentionally omitted.")
        return 1
    print("Public check passed for", count, "file snapshots; manual review is still required.")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["working-tree", "staged", "pre-push"], default="working-tree")
    parser.add_argument("--remote", help="Remote name supplied by Git (informational; update OIDs define scope).")
    args = parser.parse_args()
    try:
        root = git("rev-parse", "--show-toplevel").decode().strip()
        os.chdir(root)
        files = {"working-tree": working_files, "staged": staged_files,
                 "pre-push": lambda: push_files(sys.stdin.read())}[args.mode]()
        return check(files, denylist())
    except (CheckError, OSError, UnicodeError) as error:
        # Unexpected OS errors can contain sensitive filenames; never display them.
        print("BLOCKED:", str(error) if isinstance(error, CheckError) else "Could not complete privacy checks.")
        return 2


if __name__ == "__main__":
    sys.exit(main())
