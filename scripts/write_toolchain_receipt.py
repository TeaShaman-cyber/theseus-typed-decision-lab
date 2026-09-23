#!/usr/bin/env python3
import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import re
from pathlib import Path

LOCAL_EXPECTED = {
    "llama-cpp-python": "0.3.35",
    "semif-phase1": "0.1.0",
}

LOCK_RE = re.compile(
    r"^([A-Za-z0-9_.-]+)==([^ ]+) --hash=sha256:([0-9a-f]{64})$"
)

def normalize(name: str) -> str:
    return name.lower().replace("_", "-")

def parse_lock(path: Path) -> dict[str, dict[str, str]]:
    locked = {}
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = LOCK_RE.fullmatch(line)
        if not match:
            raise SystemExit(f"{path}:{number}: invalid lock entry")
        name, version, sha256 = match.groups()
        key = normalize(name)
        if key in locked:
            raise SystemExit(f"{path}:{number}: duplicate lock package {key}")
        locked[key] = {"version": version, "sha256": sha256}
    if not locked:
        raise SystemExit(f"{path}: empty lock")
    return locked

def distributions(site_packages: Path) -> dict[str, str]:
    found = {}
    for dist in importlib.metadata.distributions(path=[str(site_packages)]):
        name = dist.metadata.get("Name")
        if name:
            found[normalize(name)] = dist.version
    return found

def tree_digest(root: Path) -> tuple[str, int, int]:
    h = hashlib.sha256()
    count = 0
    total = 0
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root).as_posix()
        data_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        size = path.stat().st_size
        h.update(f"{rel}\0{size}\0{data_hash}\n".encode("utf-8"))
        count += 1
        total += size
    return h.hexdigest(), count, total

def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def expected_versions(lock_path: Path) -> dict[str, str]:
    expected = {name: row["version"] for name, row in parse_lock(lock_path).items()}
    expected.update(LOCAL_EXPECTED)
    return expected

def build_receipt(site_packages: Path, source_revision: str, lock_path: Path) -> dict:
    installed = distributions(site_packages)
    expected = expected_versions(lock_path)

    mismatches = {
        name: {"expected": version, "observed": installed.get(name)}
        for name, version in expected.items()
        if installed.get(name) != version
    }
    if mismatches:
        raise SystemExit(f"runtime package version mismatch: {mismatches}")

    unexpected = sorted(set(installed) - set(expected))
    if unexpected:
        raise SystemExit(f"runtime package has unexpected distributions: {unexpected}")

    forbidden = sorted(
        name for name in installed if name.startswith("nvidia-") or name == "triton"
    )
    if forbidden:
        raise SystemExit(f"CPU runtime contains forbidden CUDA packages: {forbidden}")

    digest, file_count, total_bytes = tree_digest(site_packages)
    return {
        "schema": "theseus.typed-decision-toolchain-receipt.v1",
        "status": "BUILT",
        "claim_scope": "RUNTIME_PACKAGE_IDENTITY_ONLY",
        "source_revision": source_revision,
        "lock": {
            "path": lock_path.as_posix(),
            "sha256": file_sha256(lock_path),
            "entries": len(parse_lock(lock_path)),
        },
        "runner": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "image_os": os.environ.get("ImageOS"),
            "image_version": os.environ.get("ImageVersion"),
        },
        "cpu_runtime": {
            "torch_cuda": None,
            "forbidden_cuda_packages": forbidden,
        },
        "site_packages": {
            "tree_sha256": digest,
            "file_count": file_count,
            "bytes": total_bytes,
        },
        "distributions": dict(sorted(installed.items())),
        "acceptance_authority": False,
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--site-packages", type=Path, required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    receipt = build_receipt(args.site_packages, args.source_revision, args.lock)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))

if __name__ == "__main__":
    main()
