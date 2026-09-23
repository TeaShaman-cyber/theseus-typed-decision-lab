#!/usr/bin/env python3
import argparse
import hashlib
import json
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

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--runtime", required=True)
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--gguf", required=True)
    parser.add_argument("--upstreams", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    output_rows = jsonl_rows(args.output)
    if not output_rows:
        raise SystemExit("refusing empty inference output")
    input_rows = jsonl_rows(args.fixture)
    expected_ids = [row["id"] for row in input_rows]
    result_ids = [row.get("id") for row in output_rows]
    if result_ids != expected_ids:
        raise SystemExit(f"result ids/order differ from fixture: {result_ids!r} != {expected_ids!r}")

    runtime = json.loads(Path(args.runtime).read_text(encoding="utf-8"))
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
        "upstreams": upstreams
    }
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")

if __name__ == "__main__":
    main()
