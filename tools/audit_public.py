#!/usr/bin/env python3
"""Fail publication on common secret/private-data artifacts. Not a security audit."""
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
IGNORED = {".git", "node_modules", "local", "dist", "artifacts", ".venv",
           ".ci-build", ".ci-cache", ".ci-tests", ".esphome", "__pycache__"}
FORBIDDEN_NAMES = {"secrets.yaml", ".env", "config.json", "auth.json", "db.json"}
FORBIDDEN_SUFFIXES = {".bin", ".elf", ".mp4", ".gif", ".jpg", ".jpeg", ".png", ".webp", ".tar", ".gz", ".zip"}
PATTERNS = [
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{24,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{30,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
]


def files():
    if (ROOT / ".git").exists():
        names = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
        return [ROOT / name for name in names if name]
    return [p for p in ROOT.rglob("*") if p.is_file() and not set(p.relative_to(ROOT).parts) & IGNORED]


def audit(paths):
    problems = []
    for path in paths:
        relative = path.relative_to(ROOT)
        name = relative.as_posix()
        if (path.is_symlink() or path.name in FORBIDDEN_NAMES or
                path.suffix.lower() in FORBIDDEN_SUFFIXES or
                re.fullmatch(r"state-[A-Za-z0-9_-]+\.json", path.name) or
                any(p in IGNORED for p in relative.parts) or ".local." in path.name):
            problems.append((name, "private/generated/unsupported artifact"))
            continue
        content = path.read_bytes()
        try:
            text = content.decode("utf8")
        except UnicodeDecodeError:
            if name != "firmware/fonts/DejaVuSans.ttf":
                problems.append((name, "unexpected binary asset"))
            continue
        if any(pattern.search(text) for pattern in PATTERNS):
            problems.append((name, "possible credential"))
    return problems


if __name__ == "__main__":
    source = files()
    failures = audit(source)
    for path, reason in failures:
        print(path + ": " + reason)
    if failures:
        raise SystemExit("Public source audit failed; no values printed")
    print(f"Public artifact/credential-pattern audit passed for {len(source)} files.")
