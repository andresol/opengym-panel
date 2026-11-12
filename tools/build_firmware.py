#!/usr/bin/env python3
"""Compile firmware only. Synthetic checks never use or publish private provisioning."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def synthetic_secrets():
    return {"wifi_ssid": "COMPILE_CHECK_NOT_FOR_INSTALL", "wifi_password": "compile-check-only",
            "native_api_key": base64.b64encode(bytes(range(32))).decode(),
            "native_ota_password": "synthetic-ota-not-for-install",
            "native_url": "http://gym-server.invalid:8893", "native_token": "synthetic-read-" + "r" * 40,
            "native_write_token": "synthetic-write-" + "w" * 40,
            "admin_username": "compile-check", "admin_password": "synthetic-admin-not-for-install"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--synthetic", action="store_true", help="Build isolated, non-installable CI firmware")
    parser.add_argument("--config-only", action="store_true")
    parser.add_argument("--entry", default="firmware/opengym-v3.yaml")
    args = parser.parse_args()
    version = subprocess.check_output(["esphome", "version"], text=True).strip()
    if version != "Version: 2026.10.0":
        raise SystemExit("Use ESPHome 2026.10.0 from requirements-firmware.txt")
    if not args.synthetic:
        entry = (ROOT / args.entry).resolve(strict=True)
        if not entry.is_relative_to(ROOT / "firmware"):
            raise SystemExit("Firmware entry must stay inside firmware/")
        subprocess.run(["esphome", "config", str(entry)], check=True, cwd=ROOT)
        if not args.config_only:
            subprocess.run(["esphome", "compile", str(entry)], check=True, cwd=ROOT)
        raise SystemExit(0)
    if args.entry != "firmware/opengym-v3.yaml":
        raise SystemExit("Synthetic CI uses only the generic supported V3 entry")
    with tempfile.TemporaryDirectory(prefix="opengym-public-compile-") as temporary:
        scratch = Path(temporary)
        shutil.copytree(ROOT / "firmware", scratch / "firmware",
                        ignore=shutil.ignore_patterns("secrets.yaml", "*.local.*", ".esphome", "__pycache__"))
        (scratch / "firmware/secrets.yaml").write_text("".join(k + ": " + json.dumps(v) + "\n" for k, v in synthetic_secrets().items()))
        env = {**os.environ, "ESPHOME_BUILD_PATH": str(scratch / "build"),
               "ESPHOME_DEFAULT_COMPILE_PROCESS_LIMIT": "2"}
        # Config output can contain secrets in a real build, so CI uses synthetic values only.
        subprocess.run(["esphome", "config", args.entry], cwd=scratch, env=env, check=True)
        if args.config_only:
            raise SystemExit(0)
        subprocess.run(["esphome", "compile", args.entry], cwd=scratch, env=env, check=True)
        images = list((scratch / "build").rglob("firmware.ota.bin"))
        if len(images) != 1:
            raise SystemExit("Expected exactly one fresh OTA image")
        destination = ROOT / "dist/compile-check"
        destination.mkdir(parents=True, exist_ok=True)
        outputs = []
        for name in ["firmware.ota.bin", "firmware.factory.bin", "firmware.elf"]:
            source = images[0].parent / name
            if not source.is_file() or source.stat().st_size == 0:
                raise SystemExit("Missing matching compile artifact")
            target = destination / ("SYNTHETIC-NOT-FOR-INSTALL-" + name)
            shutil.copyfile(source, target)
            outputs.append(target)
        metadata = destination / "compile.json"
        metadata.write_text(json.dumps({"synthetic": True, "installation_ready": False,
            "esphome": "2026.10.0", "project_version": json.loads((ROOT / "package.json").read_text())["version"],
            "physical_verification": False, "ota_performed": False}, indent=2) + "\n")
        outputs.append(metadata)
        (destination / "SHA256SUMS").write_text("".join(hashlib.sha256(p.read_bytes()).hexdigest() + "  " + p.name + "\n" for p in outputs))
        subprocess.run(["sha256sum", "-c", "SHA256SUMS"], cwd=destination, check=True)
        print("Synthetic compile check completed. These files must not be installed.")
