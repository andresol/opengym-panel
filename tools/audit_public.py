#!/usr/bin/env python3
"""Fail publication on common secret/private-data artifacts. Not a security audit."""
from pathlib import Path
import hashlib
import json
import re
import struct
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


def approved_documentation_image(path, content):
    """Only exact reviewed PNGs; no blanket exception for screenshots/media."""
    manifest = ROOT / "docs/images/manifest.json"
    if not manifest.is_file():
        return False
    entry = json.loads(manifest.read_text()).get("images", {}).get(path.relative_to(ROOT).as_posix())
    if not entry or path.suffix != ".png":
        return False
    relative = path.relative_to(ROOT).as_posix()
    if entry.get("kind") == "synthetic-native-lvgl-desktop-render":
        expected_size = (1280, 800)
    elif entry.get("kind") == "original-ai-exercise-illustration" and relative == "docs/images/barbell-squat-original.png":
        expected_size = (1536, 1024)
    else:
        return False
    if hashlib.sha256(content).hexdigest() != entry.get("sha256") or not content.startswith(b"\x89PNG\r\n\x1a\n"):
        return False
    offset, seen = 8, []
    while offset + 12 <= len(content):
        size = struct.unpack(">I", content[offset:offset + 4])[0]
        kind = content[offset + 4:offset + 8]
        if kind not in {b"IHDR", b"IDAT", b"IEND"} or offset + 12 + size > len(content):
            return False  # No EXIF, comments, text chunks or trailing data.
        seen.append(kind)
        if kind == b"IHDR":
            if size != 13:
                return False
            width, height = struct.unpack(">II", content[offset + 8:offset + 16])
            if (width, height) != (entry.get("width"), entry.get("height")) or (width, height) != expected_size:
                return False
        offset += 12 + size
        if kind == b"IEND":
            break
    return offset == len(content) and seen[0:1] == [b"IHDR"] and seen[-1:] == [b"IEND"] and b"IDAT" in seen


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
        if not path.is_symlink() and name.startswith("docs/images/") and path.suffix == ".png":
            if not approved_documentation_image(path, path.read_bytes()):
                problems.append((name, "unapproved or metadata-bearing documentation image"))
            continue
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
