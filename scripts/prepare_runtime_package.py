#!/usr/bin/env python3
import argparse
import hashlib
import importlib.util
import json
import subprocess
import time
from pathlib import Path


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def tree_digest(root: Path) -> tuple[str, int, int]:
    h = hashlib.sha256()
    count = 0
    total = 0
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root).as_posix()
        file_hash = sha256_file(path)
        size = path.stat().st_size
        h.update(f"{rel}\0{size}\0{file_hash}\n".encode("utf-8"))
        count += 1
        total += size
    return h.hexdigest(), count, total


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_helper(path: Path):
    spec = importlib.util.spec_from_file_location("theseus_artifact_package", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot import package helper: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_profile(profile: dict) -> dict:
    if profile.get("classification") != "PACKAGE_REQUIRED":
        raise SystemExit("SemIf runtime profile is not PACKAGE_REQUIRED")
    package = profile.get("package")
    if not isinstance(package, dict):
        raise SystemExit("SemIf runtime package is not pinned")
    required = {
        "repository", "run_id", "artifact_id", "artifact_name",
        "artifact_digest", "builder_head_sha", "tar_file", "tar_sha256",
        "lock_sha256", "tree_sha256", "cookbook_revision", "cookbook_helper",
    }
    missing = sorted(required - set(package))
    if missing:
        raise SystemExit(f"runtime package profile missing fields: {missing}")
    if not str(package["artifact_digest"]).startswith("sha256:"):
        raise SystemExit("runtime package artifact digest must be sha256")
    for key in ("tar_sha256", "lock_sha256", "tree_sha256", "builder_head_sha", "cookbook_revision"):
        value = str(package[key])
        if len(value) != 40 and key in ("builder_head_sha", "cookbook_revision"):
            raise SystemExit(f"runtime package {key} must be a 40-character Git SHA")
        if key not in ("builder_head_sha", "cookbook_revision") and len(value) != 64:
            raise SystemExit(f"runtime package {key} must be a 64-character SHA-256")
        int(value, 16)
    return package


def verify_cookbook_head(cookbook_root: Path, expected: str) -> None:
    observed = subprocess.check_output(
        ["git", "-C", str(cookbook_root), "rev-parse", "HEAD"], text=True
    ).strip()
    if observed != expected:
        raise SystemExit(f"cookbook revision mismatch: {observed} != {expected}")


def validate_build_receipt(receipt: dict, profile: dict, package: dict, runtime_dir: Path) -> dict:
    if receipt.get("schema") != "theseus.typed-decision-toolchain-receipt.v1":
        raise SystemExit("unexpected build receipt schema")
    if receipt.get("status") != "BUILT":
        raise SystemExit("toolchain build receipt is not BUILT")
    if receipt.get("claim_scope") != "RUNTIME_PACKAGE_IDENTITY_ONLY":
        raise SystemExit("unexpected toolchain receipt claim scope")
    if receipt.get("acceptance_authority") is not False:
        raise SystemExit("toolchain receipt must not carry acceptance authority")
    if receipt.get("source_revision") != profile.get("source_revision"):
        raise SystemExit("toolchain source revision mismatch")

    lock = receipt.get("lock") or {}
    if lock.get("sha256") != package.get("lock_sha256"):
        raise SystemExit("toolchain lock digest mismatch")

    site = receipt.get("site_packages") or {}
    if site.get("tree_sha256") != package.get("tree_sha256"):
        raise SystemExit("declared runtime tree digest mismatch")

    cpu = receipt.get("cpu_runtime") or {}
    if cpu.get("forbidden_cuda_packages") != []:
        raise SystemExit("toolchain contains forbidden CUDA packages")
    if cpu.get("torch_cuda") is not None:
        raise SystemExit("toolchain unexpectedly reports a CUDA Torch runtime")

    distributions = receipt.get("distributions") or {}
    expected_torch = (profile.get("runtime") or {}).get("torch")
    if distributions.get("torch") != expected_torch:
        raise SystemExit("toolchain Torch version differs from runtime profile")

    site_root = runtime_dir / "site-packages"
    if not site_root.is_dir():
        raise SystemExit("runtime package has no site-packages directory")
    observed_tree, observed_count, observed_bytes = tree_digest(site_root)
    if observed_tree != package.get("tree_sha256"):
        raise SystemExit("extracted runtime tree digest mismatch")
    if observed_count != site.get("file_count"):
        raise SystemExit("extracted runtime file count mismatch")
    if observed_bytes != site.get("bytes"):
        raise SystemExit("extracted runtime byte count mismatch")

    return {
        "tree_sha256": observed_tree,
        "file_count": observed_count,
        "bytes": observed_bytes,
        "torch": distributions.get("torch"),
        "lock_sha256": lock.get("sha256"),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--profile-key", default="semif")
    parser.add_argument("--cookbook-root", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--staging-dir", type=Path, required=True)
    parser.add_argument("--runtime-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    profiles = load_json(args.profile)
    profile = profiles["profiles"][args.profile_key]
    package = validate_profile(profile)
    verify_cookbook_head(args.cookbook_root, package["cookbook_revision"])
    helper_path = args.cookbook_root / package["cookbook_helper"]
    if not helper_path.is_file():
        raise SystemExit(f"pinned cookbook helper missing: {helper_path}")
    helper = load_helper(helper_path)

    started = time.monotonic_ns()
    metadata = helper.fetch_metadata(package)
    helper.download_archive(package, args.archive)
    verified = helper.verify_and_extract(
        package, metadata, args.archive,
        staging_dir=args.staging_dir, runtime_dir=args.runtime_dir,
    )

    receipt_path = args.runtime_dir / "build-receipt.json"
    if not receipt_path.is_file():
        raise SystemExit("toolchain build receipt missing from extracted package")
    build_receipt = load_json(receipt_path)
    runtime_verification = validate_build_receipt(
        build_receipt, profile, package, args.runtime_dir
    )
    setup_ms = (time.monotonic_ns() - started) // 1_000_000

    consumer = {
        "schema": "theseus.typed-decision-package-consumer-receipt.v1",
        "status": "READY",
        "claim_scope": "RUNTIME_PACKAGE_CONSUMPTION_ONLY",
        "setup_ms": setup_ms,
        "acceptance_authority": False,
        "profile_key": args.profile_key,
        "source_revision": profile["source_revision"],
        "cookbook": {
            "revision": package["cookbook_revision"],
            "helper": package["cookbook_helper"],
        },
        "package": package,
        "artifact": {
            "id": metadata.get("id"),
            "name": metadata.get("name"),
            "digest": metadata.get("digest"),
            "size_in_bytes": metadata.get("size_in_bytes"),
            "expired": metadata.get("expired"),
            "expires_at": metadata.get("expires_at"),
            "workflow_run": metadata.get("workflow_run"),
        },
        "verification": {
            "archive_sha256": verified["archive_sha256"],
            "tar_sha256": verified["tar_sha256"],
            "runtime": runtime_verification,
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(consumer, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(consumer, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
