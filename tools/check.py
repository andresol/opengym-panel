#!/usr/bin/env python3
"""Run deterministic source, backend and native checks using synthetic data only."""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def run(*command):
    print("CHECK", " ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


if __name__ == "__main__":
    run("npm", "test")
    run("npm", "run", "test:client")
    run("python3", "-m", "unittest", "discover", "-s", "tests/native", "-v")
    for script in ["tests/v3_hardware_check.py", "tests/native/geometry.py", "tests/native/workout_geometry.py"]:
        run("python3", script)
    with tempfile.TemporaryDirectory(prefix="opengym-panel-check-") as temporary:
        for source in [ROOT / "tests/timer_test.cpp", *sorted((ROOT / "tests/native").glob("*_test.cpp"))]:
            binary = str(Path(temporary) / source.stem)
            run("g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", str(source), "-o", binary)
            run(binary)
    run("python3", "tools/audit_public.py")
    print("All source/backend/native checks passed. No physical device was used.")
