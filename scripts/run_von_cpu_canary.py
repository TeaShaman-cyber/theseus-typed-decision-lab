#!/usr/bin/env python3
import argparse
import gc
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import resource
import sys
import time
from pathlib import Path

REQUIRED_MODEL_FILES = (
    "config.json",
    "model.safetensors",
    "option_marker.pt",
    "tokenizer.json",
    "tokenizer_config.json",
)


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def distribution_metrics(probs):
    if not isinstance(probs, dict) or len(probs) < 2:
        raise ValueError("probability distribution requires at least two options")
    clean = {}
    for key, value in probs.items():
        value = float(value)
        if not math.isfinite(value) or value < 0.0:
            raise ValueError(f"invalid probability for {key!r}: {value!r}")
        clean[str(key)] = value
    total = math.fsum(clean.values())
    if total <= 0.0 or abs(total - 1.0) > 0.02:
        raise ValueError(f"probability distribution sum is not near one: {total}")
    normalized = {key: value / total for key, value in clean.items()}
    ranked = sorted(normalized.items(), key=lambda item: (-item[1], item[0]))
    top1, top2 = ranked[0], ranked[1]
    entropy = -math.fsum(p * math.log(p) for p in normalized.values() if p > 0.0)
    return {
        "selected": top1[0],
        "entropy_nats": round(entropy, 15),
        "top1_top2_margin": round(top1[1] - top2[1], 15),
        "normalized_sum": round(math.fsum(normalized.values()), 15),
    }


def typesafe_confidence(probs):
    clean = [float(v) for v in probs.values()]
    n = len(clean)
    if n <= 1:
        return 1.0
    p_max = max(clean)
    return round(max(0.0, min(1.0, (n * p_max - 1.0) / (n - 1.0))), 6)


def compare_runs(first, repeat, reorder):
    if set(first) != set(repeat) or set(first) != set(reorder):
        raise ValueError("repeat/reorder option identity mismatch")
    first_metrics = distribution_metrics(first)
    repeat_metrics = distribution_metrics(repeat)
    reorder_metrics = distribution_metrics(reorder)
    return {
        "repeat_exact": first == repeat,
        "repeat_selected_same": first_metrics["selected"] == repeat_metrics["selected"],
        "reorder_selected_same": first_metrics["selected"] == reorder_metrics["selected"],
        "reorder_max_abs_probability_delta": round(
            max(abs(float(first[k]) - float(reorder[k])) for k in first),
            15,
        ),
    }


def load_fixture(path):
    path = Path(path)
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema") != "theseus.quasi-jev-advisory-fixture.v1":
        raise ValueError("unexpected advisory fixture schema")
    if value.get("public_synthetic") is not True:
        raise ValueError("Von feasibility probe requires public synthetic fixture")
    options = value.get("options")
    if not isinstance(options, list) or len(options) < 2:
        raise ValueError("fixture options missing")
    ids = [option.get("id") for option in options]
    if any(not isinstance(x, str) or not x for x in ids) or len(set(ids)) != len(ids):
        raise ValueError("fixture option IDs invalid")
    return value


def snapshot_manifest(root):
    root = Path(root)
    for name in REQUIRED_MODEL_FILES:
        if not (root / name).is_file():
            raise RuntimeError(f"required pinned model file missing: {name}")
    chosen = list(REQUIRED_MODEL_FILES)
    if (root / "marker_calibration.json").is_file():
        chosen.append("marker_calibration.json")
    rows = []
    total = 0
    for name in sorted(chosen):
        path = root / name
        size = path.stat().st_size
        total += size
        rows.append({"path": name, "bytes": size, "sha256": sha256_file(path)})
    return {
        "files": rows,
        "total_bytes": total,
        "manifest_sha256": sha256_bytes(canonical_bytes(rows)),
    }


def installed_source_identity(expected_revision):
    dist = importlib.metadata.distribution("von-sdk")
    raw = dist.read_text("direct_url.json")
    if not raw:
        raise RuntimeError("von-sdk direct_url.json missing; source revision cannot be verified")
    value = json.loads(raw)
    vcs = value.get("vcs_info") or {}
    commit_id = vcs.get("commit_id")
    if commit_id != expected_revision:
        raise RuntimeError(
            f"von-sdk source revision mismatch: observed={commit_id!r} expected={expected_revision!r}"
        )
    return {
        "version": dist.version,
        "direct_url": value.get("url"),
        "commit_id": commit_id,
        "requested_revision": vcs.get("requested_revision"),
    }


def question_for_options(fixture, ordered_options):
    descriptions = {option["id"]: option["description"] for option in ordered_options}
    return {
        "type": "choice",
        "instructions": fixture["question"],
        "criteria": descriptions,
    }


def answer_payload(answer):
    probs = {str(k): float(v) for k, v in answer.probabilities.items()}
    metrics = distribution_metrics(probs)
    if answer.choice != metrics["selected"]:
        raise RuntimeError(
            f"Von choice/probability argmax mismatch: choice={answer.choice!r} argmax={metrics['selected']!r}"
        )
    return {
        "choice": answer.choice,
        "probabilities": probs,
        "reported_confidence": float(answer.confidence),
        "derived": metrics,
    }


def run_choice(backend, fixture, ordered_options):
    question = question_for_options(fixture, ordered_options)
    start = time.perf_counter()
    response = backend.evaluate(
        state=fixture["state"],
        questions={"decision": question},
        model="von-1.2.0",
    )
    elapsed_ms = round((time.perf_counter() - start) * 1000.0, 3)
    answer = response.answers["decision"]
    payload = answer_payload(answer)
    payload["elapsed_ms"] = elapsed_ms
    return payload


def calibration_observation(backend, checkpoint):
    path = Path(checkpoint) / "marker_calibration.json"
    artifact = None
    if path.is_file():
        artifact = {
            "path": "marker_calibration.json",
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
        }
    if backend._calib_map:
        mode = "INPUT_CONDITIONED_MAP"
        status = "CALIBRATED"
    elif float(backend._default_temp) != 1.0:
        mode = "SCALAR_TEMPERATURE"
        status = "CALIBRATED"
    else:
        mode = "NONE"
        status = "UNCALIBRATED"
    return {
        "status": status,
        "mode": mode,
        "default_temperature": float(backend._default_temp),
        "calibration_map_active": bool(backend._calib_map),
        "independent_options": bool(backend._independent_options),
        "artifact": artifact,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--model-revision", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    fixture_path = Path(args.fixture)
    fixture = load_fixture(fixture_path)
    checkpoint = Path(args.checkpoint)
    manifest = snapshot_manifest(checkpoint)
    source_identity = installed_source_identity(args.source_revision)

    import torch
    import transformers
    from von.backends.option_marker_backend import OptionMarkerBackend

    state_dict = torch.load(
        checkpoint / "option_marker.pt",
        map_location="cpu",
        weights_only=True,
    )
    scorer_keys = sorted(key for key in state_dict if key.startswith("scorer."))
    if not scorer_keys:
        raise RuntimeError("pinned option_marker.pt has no scorer.* weights")
    del state_dict
    gc.collect()

    backend = OptionMarkerBackend(checkpoint_dir=str(checkpoint), device="cpu")
    load_start = time.perf_counter()
    model = backend._get_model()
    load_ms = round((time.perf_counter() - load_start) * 1000.0, 3)

    options = list(fixture["options"])
    original = run_choice(backend, fixture, options)
    repeat = run_choice(backend, fixture, options)
    reordered = run_choice(backend, fixture, list(reversed(options)))

    batch_questions = {
        f"decision_{index}": question_for_options(fixture, options)
        for index in range(4)
    }
    batch_start = time.perf_counter()
    batch_response = backend.evaluate(
        state=fixture["state"],
        questions=batch_questions,
        model="von-1.2.0",
    )
    batch_ms = round((time.perf_counter() - batch_start) * 1000.0, 3)
    if len(batch_response.answers) != 4:
        raise RuntimeError("Von batch probe did not return four answers")

    option_ids = [option["id"] for option in options]
    for payload in (original, repeat, reordered):
        if set(payload["probabilities"]) != set(option_ids):
            raise RuntimeError("Von probability distribution does not cover the registered option set")

    stability = compare_runs(
        original["probabilities"],
        repeat["probabilities"],
        reordered["probabilities"],
    )
    cal = calibration_observation(backend, checkpoint)
    reported = original["reported_confidence"]
    top_margin = original["derived"]["top1_top2_margin"]
    chance_formula = typesafe_confidence(original["probabilities"])

    peak_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    peak_rss_bytes = int(peak_rss * 1024) if sys.platform.startswith("linux") else int(peak_rss)

    receipt = {
        "schema": "theseus.von-cpu-feasibility.v1",
        "claim_scope": "RUNTIME_FEASIBILITY_ONLY",
        "issue": 28,
        "repository_sha": os.environ.get("GITHUB_SHA"),
        "identity": {
            "source_repo": "wfzyx/von",
            "source_revision": args.source_revision,
            "source_install": source_identity,
            "model_repo": "wfzyx/von",
            "model_revision": args.model_revision,
            "model_snapshot": manifest,
        },
        "fixture": {
            "id": fixture["id"],
            "path": fixture_path.as_posix(),
            "sha256": sha256_file(fixture_path),
            "state_sha256": sha256_bytes(fixture["state"].encode("utf-8")),
            "question_sha256": sha256_bytes(fixture["question"].encode("utf-8")),
            "option_set_sha256": sha256_bytes(canonical_bytes(fixture["options"])),
            "question_pack_sha256": sha256_bytes(canonical_bytes({
                "state": fixture["state"],
                "question": fixture["question"],
                "options": fixture["options"],
            })),
        },
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "torch": torch.__version__,
            "transformers": transformers.__version__,
            "device": "cpu",
            "hf_hub_offline": os.environ.get("HF_HUB_OFFLINE") == "1",
            "transformers_offline": os.environ.get("TRANSFORMERS_OFFLINE") == "1",
            "model_load_ms": load_ms,
            "peak_rss_bytes": peak_rss_bytes,
            "scorer_weight_key_count": len(scorer_keys),
            "scorer_weight_keys_sha256": sha256_bytes(canonical_bytes(scorer_keys)),
            "digit_split": bool(getattr(model, "digit_split", False)),
        },
        "calibration": cal,
        "observations": {
            "original": original,
            "repeat": repeat,
            "reordered": reordered,
            "batch_4_elapsed_ms": batch_ms,
            "stability": stability,
            "confidence_semantics": {
                "von_reported": reported,
                "our_top1_top2_margin": top_margin,
                "typesafe_chance_baseline_formula": chance_formula,
                "reported_minus_top1_top2": round(reported - top_margin, 15),
                "reported_minus_typesafe_formula": round(reported - chance_formula, 15),
            },
        },
        "classification": "CPU_FEASIBLE",
        "acceptance_authority": False,
        "permission_authority": False,
        "verification_authority": False,
        "promotion_authority": False,
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "classification": receipt["classification"],
        "choice": original["choice"],
        "repeat_exact": stability["repeat_exact"],
        "reorder_selected_same": stability["reorder_selected_same"],
        "reorder_max_abs_probability_delta": stability["reorder_max_abs_probability_delta"],
        "calibration": cal["status"],
        "model_load_ms": load_ms,
        "peak_rss_bytes": peak_rss_bytes,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
