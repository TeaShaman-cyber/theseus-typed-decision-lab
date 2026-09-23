#!/usr/bin/env python3
import json
import os
import platform
import shutil
import sys
from pathlib import Path

def mem_total_kib():
    path = Path("/proc/meminfo")
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("MemTotal:"):
            return int(line.split()[1])
    return None

def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: capture_runtime.py OUTPUT.json")
    target = Path(sys.argv[1])
    target.parent.mkdir(parents=True, exist_ok=True)
    disk = shutil.disk_usage(".")
    payload = {
        "schema": "theseus.typed-decision-runtime.v1",
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "cpu_count": os.cpu_count(),
        "mem_total_kib": mem_total_kib(),
        "disk_total_bytes": disk.total,
        "disk_free_bytes": disk.free,
        "github": {
            "runner_os": os.environ.get("RUNNER_OS"),
            "runner_arch": os.environ.get("RUNNER_ARCH"),
            "run_id": os.environ.get("GITHUB_RUN_ID"),
            "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
            "sha": os.environ.get("GITHUB_SHA")
        }
    }
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

if __name__ == "__main__":
    main()
