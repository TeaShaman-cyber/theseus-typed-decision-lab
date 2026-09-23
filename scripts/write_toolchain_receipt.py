#!/usr/bin/env python3
import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
from pathlib import Path

EXPECTED = {
    "torch": "2.10.0+cpu",
    "transformers": "5.17.0",
    "accelerate": "1.12.0",
    "safetensors": "0.8.0",
    "huggingface-hub": "1.31.0",
    "tokenizers": "0.23.2",
    "numpy": "2.2.6",
    "sentencepiece": "0.2.1",
    "protobuf": "7.36.1",
    "llama-cpp-python": "0.3.35",
    "semif-phase1": "0.1.0",
}

def normalize(name: str) -> str:
    return name.lower().replace("_", "-")

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
        h.update(f"{rel}\\0{size}\\0{data_hash}\n".encode("utf-8"))
        count += 1
        total += size
    return h.hexdigest(), count, total

def build_receipt(site_packages: Path, source_revision: str) -> dict:
    installed = distributions(site_packages)
    missing = {k: v for k, v in EXPECTED.items() if installed.get(k) != v}
    if missing:
        raise SystemExit(f"runtime package version mismatch: {missing}")

    forbidden = sorted(name for name in installed if name.startswith("nvidia-") or name == "triton")
    if forbidden:
        raise SystemExit(f"CPU runtime contains forbidden CUDA packages: {forbidden}")

    digest, file_count, total_bytes = tree_digest(site_packages)
    return {
        "schema": "theseus.typed-decision-toolchain-receipt.v1",
        "status": "BUILT",
        "claim_scope": "RUNTIME_PACKAGE_IDENTITY_ONLY",
        "source_revision": source_revision,
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
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    receipt = build_receipt(args.site_packages, args.source_revision)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2, sort_keys=True))

if __name__ == "__main__":
    main()
