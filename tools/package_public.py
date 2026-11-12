#!/usr/bin/env python3
"""Package only reviewed tracked source, never installation files or firmware."""
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile

from audit_public import ROOT, audit, files


if __name__ == "__main__":
    source = files()
    if not (ROOT / ".git").exists() or audit(source):
        raise SystemExit("A clean, audited standalone Git repository is required")
    if subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT).strip():
        raise SystemExit("Commit reviewed source before packaging")
    version = json.loads((ROOT / "package.json").read_text())["version"]
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    output = ROOT / "dist"
    output.mkdir(exist_ok=True)
    archive = output / ("opengym-panel-" + version + "-source.tar.gz")
    with tarfile.open(archive, "w:gz") as stream:
        for path in sorted(source):
            stream.add(path, arcname="opengym-panel/" + path.relative_to(ROOT).as_posix(), recursive=False)
    manifest = output / "release.json"
    manifest.write_text(json.dumps({"project": "opengym-panel", "version": version,
        "source_commit": commit, "track": "community-source-preview", "source_files": len(source),
        "provisioning_included": False, "firmware_included": False, "exercise_media_included": False,
        "stable_community_release": False}, indent=2) + "\n")
    (output / "SHA256SUMS").write_text("".join(hashlib.sha256(p.read_bytes()).hexdigest() + "  " + p.name + "\n" for p in [archive, manifest]))
    subprocess.run(["sha256sum", "-c", "SHA256SUMS"], cwd=output, check=True)
    print(archive)
