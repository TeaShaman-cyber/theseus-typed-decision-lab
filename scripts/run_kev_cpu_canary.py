#!/usr/bin/env python3
import argparse
import importlib.metadata
import json
import os
import platform
import resource
import time
from pathlib import Path

import torch
from kev.checkpoint import Checkpoint, LoadOptions

EXPECTED_BASE = "Qwen/Qwen3.5-0.8B-Base"
EXPECTED_BASE_REV = "dc7cdfe2ee4154fa7e30f5b51ca41bfa40174e68"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--threads", type=int, default=4)
    args = parser.parse_args()

    torch.set_num_threads(args.threads)
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))

    started = time.monotonic()
    ck = Checkpoint(args.checkpoint)
    if ck.meta.base != EXPECTED_BASE:
        raise SystemExit(f"unexpected Kev base: {ck.meta.base}")
    if ck.meta.base_revision != EXPECTED_BASE_REV:
        raise SystemExit(f"unexpected Kev base revision: {ck.meta.base_revision}")

    load_started = time.monotonic()
    tok, model = ck.load(
        "cpu",
        LoadOptions(dtype=torch.float32, merge=False, backend="torch"),
    )
    load_seconds = time.monotonic() - load_started

    enc = model.encode(tok, fixture)
    forward_started = time.monotonic()
    probs = model.probs(enc)
    forward_seconds = time.monotonic() - forward_started

    rows = [p.detach().cpu().tolist() for p in probs]
    if len(rows) != len(fixture["questions"]):
        raise SystemExit("Kev output row count mismatch")
    for row, question in zip(rows, fixture["questions"]):
        if len(row) != len(question["options"]):
            raise SystemExit("Kev option count mismatch")
        if abs(sum(row) - 1.0) > 1e-5:
            raise SystemExit("Kev probabilities are not normalized")

    peak_rss_kib = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    receipt = {
        "schema": "theseus.kev-cpu-feasibility.v1",
        "claim_scope": "RUNTIME_FEASIBILITY_ONLY",
        "status": "PASS",
        "acceptance_authority": False,
        "checkpoint": {
            "requested": args.checkpoint,
            "base": ck.meta.base,
            "base_revision": ck.meta.base_revision,
            "temperature": ck.meta.temperature,
            "weights_dtype": ck.meta.weights_dtype,
        },
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "cpu_count": os.cpu_count(),
            "threads": args.threads,
            "torch": torch.__version__,
            "torch_cuda": torch.version.cuda,
            "transformers": importlib.metadata.version("transformers"),
            "peft": importlib.metadata.version("peft"),
            "load_seconds": load_seconds,
            "forward_seconds": forward_seconds,
            "total_seconds": time.monotonic() - started,
            "peak_rss_kib": peak_rss_kib,
        },
        "fixture": fixture,
        "probabilities": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
