#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import time
from pathlib import Path
from typing import Any


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def distribution_metrics(probs: dict[str, float]) -> dict[str, float]:
    values = [float(x) for x in probs.values()]
    if len(values) < 2:
        raise ValueError("need at least two options")
    total = math.fsum(values)
    if not math.isclose(total, 1.0, rel_tol=0.0, abs_tol=1e-6):
        raise ValueError(f"probabilities not normalized: {total}")
    ordered = sorted(values, reverse=True)
    entropy = -math.fsum(p * math.log(p) for p in values if p > 0.0)
    return {
        "entropy_nats": entropy,
        "top1_top2_margin": ordered[0] - ordered[1],
    }


def select_option(probs: dict[str, float]) -> tuple[str | None, str]:
    best = max(probs.values())
    winners = [key for key, value in probs.items() if value == best]
    if len(winners) != 1:
        return None, "TIE"
    return winners[0], "SELECTED"


def validate_surface(manifest_dir: Path, entry: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    path = manifest_dir / entry["model_input_path"]
    if sha256_file(path) != entry["model_input_sha256"]:
        raise ValueError(f"surface file hash mismatch: {entry['surface_id']}")
    pack = load_json(path)
    if set(pack) != {"state", "question", "options"}:
        raise ValueError(f"unexpected model-input keys: {entry['surface_id']}")
    if sha256_text(pack["state"]) != entry["state_sha256"]:
        raise ValueError(f"state hash mismatch: {entry['surface_id']}")
    if sha256_text(pack["question"]) != entry["question_sha256"]:
        raise ValueError(f"question hash mismatch: {entry['surface_id']}")
    if sha256_bytes(canonical_bytes(pack["options"])) != entry["option_set_sha256"]:
        raise ValueError(f"option hash mismatch: {entry['surface_id']}")
    if sha256_bytes(canonical_bytes(pack)) != entry["question_pack_sha256"]:
        raise ValueError(f"question-pack hash mismatch: {entry['surface_id']}")
    ids = [x["id"] for x in pack["options"]]
    if len(ids) != len(set(ids)):
        raise ValueError(f"duplicate option ids: {entry['surface_id']}")
    return path, pack


def runtime_versions() -> dict[str, Any]:
    import torch

    packages = {}
    for name in (
        "anyjev",
        "numpy",
        "torch",
        "transformers",
        "huggingface-hub",
        "tokenizers",
        "safetensors",
    ):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "packages": packages,
        "torch_cuda_available": bool(torch.cuda.is_available()),
    }


def safe_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def run(args: argparse.Namespace) -> dict[str, Any]:
    import numpy as np
    from anyjev import Decider, Question
    from anyjev.backends.hf import HFBackend

    manifest_path = Path(args.manifest)
    manifest = load_json(manifest_path)
    if manifest.get("schema") != "theseus.anyjev-hbr1-manifest.v1":
        raise ValueError("HBR-1 manifest schema mismatch")
    if manifest.get("outcome_escrow_in_candidate_input") is not False:
        raise ValueError("outcome escrow boundary not preserved")

    candidate = manifest["candidate"]
    if candidate["levels"] != ["raw", "L0"]:
        raise ValueError("HBR-1 level contract mismatch")
    if importlib.metadata.version("anyjev") != candidate["anyjev_package_version"]:
        raise ValueError("installed AnyJev package version mismatch")

    anyjev_resolution = load_json(Path(args.anyjev_resolution))
    if anyjev_resolution.get("repository") != candidate["anyjev_repository"]:
        raise ValueError("AnyJev source repository mismatch")
    if anyjev_resolution.get("requested_revision") != candidate["anyjev_revision"]:
        raise ValueError("AnyJev requested revision mismatch")
    if anyjev_resolution.get("observed_revision") != candidate["anyjev_revision"]:
        raise ValueError("AnyJev source revision mismatch")

    model_resolution = load_json(Path(args.model_resolution))
    if model_resolution.get("repository") != candidate["base_model_repository"]:
        raise ValueError("base model repository mismatch")
    if model_resolution.get("requested_revision") != candidate["base_model_revision"]:
        raise ValueError("base model requested revision mismatch")
    if model_resolution.get("observed_revision") != candidate["base_model_revision"]:
        raise ValueError("base model revision mismatch")

    runtime = runtime_versions()
    if runtime["torch_cuda_available"]:
        raise ValueError("HBR-1 CPU-only contract violated: CUDA is available")
    expected_versions = {
        "anyjev": candidate["anyjev_package_version"],
        "numpy": "2.2.6",
        "torch": "2.10.0+cpu",
        "transformers": "5.17.0",
        "huggingface-hub": "1.31.0",
        "tokenizers": "0.23.2",
        "safetensors": "0.8.0",
    }
    for name, expected in expected_versions.items():
        if runtime["packages"].get(name) != expected:
            raise ValueError(
                f"runtime version mismatch for {name}: "
                f"{runtime['packages'].get(name)} != {expected}"
            )

    model_dir = Path(args.model_dir)
    if not model_dir.is_dir():
        raise ValueError("model directory missing")

    load_started = time.perf_counter()
    backend = HFBackend(
        str(model_dir),
        device="cpu",
        dtype="float32",
        batch_size=1,
        trust_remote_code=False,
    )
    load_ms = round((time.perf_counter() - load_started) * 1000.0, 3)
    if str(backend.device) != "cpu":
        raise ValueError(f"unexpected backend device: {backend.device}")

    results = []
    manifest_dir = manifest_path.parent
    for entry in manifest["surfaces"]:
        surface_path, pack = validate_surface(manifest_dir, entry)
        projected_options = [
            f"{option['id']}: {option['description']}"
            for option in pack["options"]
        ]
        question = Question.choice(
            pack["question"],
            projected_options,
            name=entry["surface_id"],
        )

        for requested_level in ("raw", "L0"):
            decider = Decider(
                backend,
                level=requested_level,
                prior="none",
                max_permutations=None,
                combine="logmean",
                shared_prefix=False,
                adaptive_shifts=False,
                canonical_order=False,
            )
            started = time.perf_counter()
            decision = decider.decide(
                pack["state"],
                [question],
                level=requested_level,
            )[0]
            elapsed_ms = round((time.perf_counter() - started) * 1000.0, 3)

            if decision.level != requested_level:
                raise ValueError(
                    f"served level mismatch for {entry['surface_id']}: "
                    f"{decision.level} != {requested_level}"
                )
            if len(decision.probs) != len(pack["options"]):
                raise ValueError(f"probability shape mismatch: {entry['surface_id']}")

            probs = {
                option["id"]: float(decision.probs[i])
                for i, option in enumerate(pack["options"])
            }
            selected, status = select_option(probs)
            metrics = distribution_metrics(probs)
            diag = decision.diagnostics

            expected_permutations = 1 if requested_level == "raw" else len(pack["options"])
            if int(diag.get("permutations", -1)) != expected_permutations:
                raise ValueError(
                    f"permutation count mismatch for {entry['surface_id']} "
                    f"{requested_level}: {diag.get('permutations')} "
                    f"!= {expected_permutations}"
                )
            if requested_level == "L0":
                if diag.get("prior_method") != "none":
                    raise ValueError(
                        f"L0 prior unexpectedly active for {entry['surface_id']}: "
                        f"{diag.get('prior_method')}"
                    )
                if float(diag.get("prior_strength", -1.0)) != 0.0:
                    raise ValueError("L0 prior strength unexpectedly nonzero")

            p_pos_raw = diag.get("p_pos_raw")
            p_pos_raw_list = (
                np.asarray(p_pos_raw, dtype=float).tolist()
                if p_pos_raw is not None
                else None
            )
            results.append(
                {
                    "surface_id": entry["surface_id"],
                    "surface_input_path": surface_path.as_posix(),
                    "surface_input_sha256": entry["model_input_sha256"],
                    "requested_level": requested_level,
                    "served_level": decision.level,
                    "option_projection": "ID_COLON_DESCRIPTION_V1",
                    "option_ids": [x["id"] for x in pack["options"]],
                    "probabilities": probs,
                    "selected_option": selected,
                    "decision_status": status,
                    "distribution_metrics": metrics,
                    "diagnostics": {
                        "answer_mass": safe_float(diag.get("answer_mass")),
                        "permutations": int(diag["permutations"]),
                        "perms": diag.get("perms"),
                        "prior_method": diag.get("prior_method"),
                        "prior_strength": safe_float(diag.get("prior_strength")),
                        "order_flip_raw": safe_float(diag.get("order_flip_raw")),
                        "order_flip_l0": safe_float(diag.get("order_flip_l0")),
                        "p_pos_raw": p_pos_raw_list,
                    },
                    "elapsed_ms": elapsed_ms,
                }
            )

    return {
        "schema": "theseus.anyjev-hbr1-candidate.v1",
        "claim_scope": "ADVISORY_HISTORICAL_BLIND_REPLAY_ONLY",
        "repository_sha": os.environ.get("GITHUB_SHA"),
        "run_id": os.environ.get("GITHUB_RUN_ID"),
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "manifest": {
            "path": manifest_path.as_posix(),
            "sha256": sha256_file(manifest_path),
        },
        "source": manifest["source"],
        "candidate": candidate,
        "execution_contract": {
            "device": "cpu",
            "dtype": "float32",
            "backend_batch_size": 1,
            "prior": "none",
            "adaptive_shifts": False,
            "canonical_order": False,
            "max_permutations": None,
            "combine": "logmean",
            "shared_prefix": False,
            "l0_scope": "FULL_CYCLIC_PERMUTATION_MARGINALIZATION_ONLY",
        },
        "anyjev_resolution": anyjev_resolution,
        "model_resolution": model_resolution,
        "runtime": runtime,
        "model_load_ms": load_ms,
        "results": results,
        "outcome_escrow_consumed": False,
        "calibration_claim": False,
        "jev_equivalence_claim": False,
        "acceptance_authority": False,
        "permission_authority": False,
        "verification_authority": False,
        "promotion_authority": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the preregistered AnyJev HBR-1 raw/L0 CPU replay."
    )
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--model-dir", required=True)
    parser.add_argument("--anyjev-resolution", required=True)
    parser.add_argument("--model-resolution", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    receipt = run(args)
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
