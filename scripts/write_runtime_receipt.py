#!/usr/bin/env python3
import argparse
import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def jsonl_rows(path):
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows

def validate_runtime_package_receipt(receipt):
    if receipt.get("schema") != "theseus.typed-decision-package-consumer-receipt.v1":
        raise SystemExit("unexpected runtime package receipt schema")
    if receipt.get("status") != "READY":
        raise SystemExit("runtime package receipt is not READY")
    if receipt.get("claim_scope") != "RUNTIME_PACKAGE_CONSUMPTION_ONLY":
        raise SystemExit("unexpected runtime package receipt claim scope")
    if receipt.get("acceptance_authority") is not False:
        raise SystemExit("runtime package receipt must not carry acceptance authority")

    package = receipt.get("package")
    verification = receipt.get("verification")
    if not isinstance(package, dict) or not isinstance(verification, dict):
        raise SystemExit("runtime package receipt is incomplete")

    artifact = receipt.get("artifact") or {}
    if artifact.get("id") != package.get("artifact_id"):
        raise SystemExit("runtime package artifact id mismatch")
    if artifact.get("digest") != package.get("artifact_digest"):
        raise SystemExit("runtime package artifact digest mismatch")
    if artifact.get("expired") is not False:
        raise SystemExit("runtime package artifact is expired or expiry is unknown")

    if verification.get("tar_sha256") != package.get("tar_sha256"):
        raise SystemExit("runtime package tar digest mismatch")
    runtime = verification.get("runtime") or {}
    if runtime.get("tree_sha256") != package.get("tree_sha256"):
        raise SystemExit("runtime package tree digest mismatch")
    if runtime.get("lock_sha256") != package.get("lock_sha256"):
        raise SystemExit("runtime package lock digest mismatch")

    setup_ms = receipt.get("setup_ms")
    if isinstance(setup_ms, bool) or not isinstance(setup_ms, int) or setup_ms < 0:
        raise SystemExit("runtime package setup_ms must be a non-negative integer")


def validate_semif_output(input_rows, output_rows):
    if len(output_rows) != len(input_rows):
        raise SystemExit(
            f"output row count differs from fixture: {len(output_rows)} != {len(input_rows)}"
        )
    for input_row, output_row in zip(input_rows, output_rows):
        row_id = input_row["id"]
        if not isinstance(output_row, dict):
            raise SystemExit(f"row {row_id}: output is not an object")
        if output_row.get("id") != row_id:
            raise SystemExit(
                f"row id/order differs from fixture: {output_row.get('id')!r} != {row_id!r}"
            )

        expected_options = [item["id"] for item in input_row["options"]]
        option_ids = output_row.get("option_ids")
        if option_ids != expected_options:
            raise SystemExit(
                f"row {row_id}: option_ids differ from fixture: {option_ids!r} != {expected_options!r}"
            )

        probabilities = output_row.get("probabilities")
        if not isinstance(probabilities, list) or len(probabilities) != len(expected_options):
            raise SystemExit(f"row {row_id}: invalid probabilities shape")
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value < 0.0
            or value > 1.0
            for value in probabilities
        ):
            raise SystemExit(f"row {row_id}: probabilities must be finite numbers in [0, 1]")
        if not math.isclose(sum(probabilities), 1.0, rel_tol=0.0, abs_tol=1e-6):
            raise SystemExit(
                f"row {row_id}: probabilities are not normalized: sum={sum(probabilities)!r}"
            )

        logits = output_row.get("option_logits")
        if not isinstance(logits, list) or len(logits) != len(expected_options):
            raise SystemExit(f"row {row_id}: invalid option_logits shape")
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            for value in logits
        ):
            raise SystemExit(f"row {row_id}: option_logits must be finite numbers")

        model = output_row.get("model")
        if not isinstance(model, dict):
            raise SystemExit(f"row {row_id}: missing model metadata")
        if model.get("backend") != "llamacpp":
            raise SystemExit(
                f"row {row_id}: expected llamacpp backend, got {model.get('backend')!r}"
            )

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--runtime", required=True)
    parser.add_argument("--runtime-package", required=True)
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--gguf", required=True)
    parser.add_argument("--upstreams", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    output_rows = jsonl_rows(args.output)
    if not output_rows:
        raise SystemExit("refusing empty inference output")
    input_rows = jsonl_rows(args.fixture)
    validate_semif_output(input_rows, output_rows)
    result_ids = [row["id"] for row in output_rows]

    runtime = json.loads(Path(args.runtime).read_text(encoding="utf-8"))
    runtime_package = json.loads(Path(args.runtime_package).read_text(encoding="utf-8"))
    validate_runtime_package_receipt(runtime_package)
    upstreams = json.loads(Path(args.upstreams).read_text(encoding="utf-8"))
    gguf = Path(args.gguf)
    receipt = {
        "schema": "theseus.typed-decision-runtime-receipt.v1",
        "claim_scope": "RUNTIME_FEASIBILITY_ONLY",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "repository": os.environ.get("GITHUB_REPOSITORY"),
        "repository_sha": os.environ.get("GITHUB_SHA"),
        "run_id": os.environ.get("GITHUB_RUN_ID"),
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "duration_ms": int(os.environ["DURATION_MS"]) if os.environ.get("DURATION_MS") else None,
        "fixture": {
            "path": args.fixture,
            "sha256": sha256(args.fixture),
            "rows": len(input_rows)
        },
        "output": {
            "path": args.output,
            "sha256": sha256(args.output),
            "rows": len(output_rows),
            "ids": result_ids
        },
        "gguf": {
            "path": gguf.name,
            "bytes": gguf.stat().st_size,
            "sha256": sha256(gguf)
        },
        "runtime": runtime,
        "runtime_package": runtime_package,
        "upstreams": upstreams
    }
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")

if __name__ == "__main__":
    main()
