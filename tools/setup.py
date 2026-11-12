#!/usr/bin/env python3
"""Create a private installation directory. Never starts services or flashes a panel."""
import argparse
import base64
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import shutil
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]


def origin(value):
    parsed = urlsplit(value)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname or
            parsed.username is not None or parsed.password is not None or
            parsed.path not in {"", "/"} or parsed.query or parsed.fragment or
            any(c.isspace() for c in value)):
        raise ValueError("Use an HTTP(S) origin without credentials or a path")
    if parsed.port is not None and not 0 < parsed.port <= 65535:
        raise ValueError("Invalid port")
    return value.rstrip("/")


def profiles_from(path):
    values = json.loads(Path(path).read_text())
    if not isinstance(values, list) or not 1 <= len(values) <= 8:
        raise ValueError("Choose one to eight existing, non-administrator profiles")
    slugs, identities = set(), set()
    for item in values:
        if not isinstance(item, dict) or set(item) != {"slug", "uid", "name"}:
            raise ValueError("Each profile needs exactly slug, uid and name")
        if (not isinstance(item["slug"], str) or
                not re.fullmatch(r"[a-z][a-z0-9-]{0,30}", item["slug"]) or
                not isinstance(item["uid"], str) or
                not re.fullmatch(r"[A-Za-z0-9_-]{8,80}", item["uid"]) or
                not isinstance(item["name"], str) or not item["name"].strip() or
                len(item["name"]) > 80 or any(ord(c) < 32 for c in item["name"]) or
                item["uid"] == "REPLACE_WITH_YOUR_PROFILE_UID" or
                item["slug"] in slugs or item["uid"] in identities):
            raise ValueError("Invalid, placeholder or duplicate profile")
        slugs.add(item["slug"])
        identities.add(item["uid"])
    return values


def write_private(path, content, uid, gid):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    if os.geteuid() == 0:
        os.chown(path, uid, gid)


def prepare(args):
    profiles = profiles_from(args.profiles)
    api_url, panel_url = origin(args.api_url), origin(args.panel_url)
    if urlsplit(panel_url).scheme != "http":
        raise ValueError("The ESP32 transport currently supports a trusted-LAN HTTP panel URL")
    ZoneInfo(args.timezone)
    address = ipaddress.ip_address(args.bind_address)
    if address.is_unspecified or address.is_multicast or address.is_loopback:
        raise ValueError("Bind to one explicit LAN address reachable by the panel")
    data = Path(args.data_dir).resolve(strict=True)
    if not data.is_dir():
        raise ValueError("OpenGym data directory is missing")
    for item in profiles:
        state = data / ("state-" + item["uid"] + ".json")
        if not state.is_file() or state.is_symlink():
            raise ValueError("A selected profile state file does not exist")
    output = Path(args.output).absolute()
    if output.exists() or output.is_symlink():
        raise FileExistsError("Installation output already exists; nothing overwritten")
    if args.uid < 1 or args.gid < 0:
        raise ValueError("Use a non-root container UID and a valid GID")
    if os.geteuid() != 0 and (args.uid != os.getuid() or args.gid != os.getgid()):
        raise ValueError("Use your own UID/GID, or run setup as root to set file ownership")
    output.mkdir(mode=0o700, parents=True)
    try:
        for folder in [output, output / "sessions", output / "owned-media"]:
            folder.mkdir(exist_ok=True, mode=0o700)
            if os.geteuid() == 0:
                os.chown(folder, args.uid, args.gid)
        read_key, upstream_key, write_key = [secrets.token_hex(32) for _ in range(3)]
        session = {"profiles": profiles, "apiOrigin": api_url,
                   "readToken": upstream_key, "writeToken": write_key}
        native = {"token": read_key, "upstreamToken": upstream_key,
                  "writeToken": write_key, "mediaMode": "placeholder"}
        credentials = {
            "wifi_ssid": "REPLACE_WITH_YOUR_WIFI_NAME",
            "wifi_password": "REPLACE_WITH_YOUR_WIFI_PASSWORD",
            "native_api_key": base64.b64encode(secrets.token_bytes(32)).decode(),
            "native_ota_password": secrets.token_urlsafe(32),
            "native_url": panel_url, "native_token": read_key,
            "native_write_token": write_key,
            "admin_username": "admin", "admin_password": secrets.token_urlsafe(24),
        }
        files = {"sessions.json": json.dumps(session, indent=2) + "\n",
                 "native.json": json.dumps(native, indent=2) + "\n",
                 "secrets.yaml": "".join(k + ": " + json.dumps(v) + "\n" for k, v in credentials.items())}
        common = {"restart": "unless-stopped", "read_only": True,
                  "user": f"{args.uid}:{args.gid}", "cap_drop": ["ALL"],
                  "security_opt": ["no-new-privileges:true"], "pids_limit": 64,
                  "logging": {"driver": "json-file", "options": {"max-size": "5m", "max-file": "2"}}}
        def mount(source, target, readonly=True):
            return {"type": "bind", "source": str(source), "target": target,
                    "read_only": readonly, "bind": {"create_host_path": False}}
        services = {
            "sessions": {**common, "build": {"context": str(ROOT), "dockerfile": "sessions/Dockerfile"},
                "mem_limit": "256m", "cpus": 1,
                "environment": {"SESSION_CONFIG": "/run/panel/sessions.json", "DATA_DIR": "/data",
                    "SESSION_DIR": "/sessions", "PANEL_TIMEZONE": args.timezone, "PANEL_LANGUAGE": "nb"},
                "extra_hosts": ["host.docker.internal:host-gateway"],
                "volumes": [mount(data, "/data"), mount(output / "sessions.json", "/run/panel/sessions.json"),
                            mount(output / "sessions", "/sessions", False)],
                "healthcheck": {"test": ["CMD", "node", "-e", "fetch('http://127.0.0.1:8894/health').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"],
                                "interval": "30s", "timeout": "5s", "retries": 3}},
            "native": {**common, "build": {"context": str(ROOT), "dockerfile": "native/Dockerfile"},
                "mem_limit": "192m", "cpus": 1,
                "depends_on": {"sessions": {"condition": "service_healthy"}},
                "environment": {"PANEL_CONFIG": "/run/panel/native.json", "MEDIA_DIR": "/owned-media",
                    "CATALOGUE_MEDIA_DIR": "/owned-media", "UPSTREAM": "http://sessions:8894",
                    "PYTHONDONTWRITEBYTECODE": "1"},
                "ports": [f"{args.bind_address}:8893:8893"],
                "volumes": [mount(output / "native.json", "/run/panel/native.json"),
                            mount(output / "owned-media", "/owned-media")],
                "healthcheck": {"test": ["CMD", "python3", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8893/health',timeout=3)"],
                                "interval": "30s", "timeout": "5s", "retries": 3}},
        }
        files["compose.yaml"] = json.dumps({"name": "opengym-panel", "services": services}, indent=2) + "\n"
        for name, content in files.items():
            write_private(output / name, content, args.uid, args.gid)
    except Exception:
        # Only the fresh directory created by this call may be rolled back.
        shutil.rmtree(output)
        raise
    return output


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--profiles", required=True)
    result.add_argument("--data-dir", required=True)
    result.add_argument("--api-url", required=True)
    result.add_argument("--panel-url", required=True)
    result.add_argument("--bind-address", required=True)
    result.add_argument("--output", required=True)
    result.add_argument("--timezone", default="Europe/Oslo")
    result.add_argument("--uid", type=int, default=os.getuid() or 1000)
    result.add_argument("--gid", type=int, default=os.getgid() or 1000)
    return result


if __name__ == "__main__":
    cli = parser()
    try:
        directory = prepare(cli.parse_args())
        print("Private installation created at", directory)
        print("Edit Wi-Fi in secrets.yaml. Nothing started, paired, built or flashed.")
    except (ValueError, OSError, KeyError) as error:
        cli.exit(2, str(error) + "\n")
