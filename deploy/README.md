# Companion deployment

Generate deployment files using `python3 tools/setup.py` on your companion host.
See [INSTALL.md](../docs/INSTALL.md). There is intentionally no shared deployment
token or household-specific Compose file in this directory.

The generated private Compose file runs `sessions/Dockerfile` and `native/Dockerfile`
with separate configs. Only the adapter's explicitly bound LAN port is published;
the session service is internal. The OpenGym source-state mount is read-only and
the session-store mount is separate and writable. Docker build contexts exclude
secrets, private local files and provisioned binaries via `.dockerignore`.
