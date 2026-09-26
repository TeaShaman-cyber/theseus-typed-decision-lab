#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "fixtures/advisory/registry.json"
UPSTREAMS = ROOT / "config/upstreams.json"


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n" for row in rows), encoding="utf-8")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError("JSONL row must be an object")
        rows.append(row)
    return rows


def safe_registered_fixture(fixture_id: str) -> tuple[Path, dict[str, Any]]:
    registry = load_json(REGISTRY)
    if registry.get("schema") != "theseus.quasi-jev-advisory-registry.v1":
        raise ValueError("advisory registry schema mismatch")
    rel = (registry.get("fixtures") or {}).get(fixture_id)
    if not isinstance(rel, str):
        raise ValueError(f"unknown registered advisory fixture: {fixture_id}")
    pure = Path(rel)
    if pure.is_absolute() or ".." in pure.parts or not rel.startswith("fixtures/advisory/"):
        raise ValueError("unsafe advisory fixture path")
    path = ROOT / pure
    fixture = load_json(path)
    if fixture.get("schema") != "theseus.quasi-jev-advisory-fixture.v1":
        raise ValueError("advisory fixture schema mismatch")
    if fixture.get("id") != fixture_id or fixture.get("public_synthetic") is not True:
        raise ValueError("advisory fixture identity/scope mismatch")
    if set(fixture) != {"schema", "id", "public_synthetic", "state", "question", "options"}:
        raise ValueError("advisory fixture keys mismatch")
    if not isinstance(fixture["state"], str) or not fixture["state"].strip():
        raise ValueError("advisory state missing")
    if not isinstance(fixture["question"], str) or not fixture["question"].strip():
        raise ValueError("advisory question missing")
    options = fixture["options"]
    if not isinstance(options, list) or not 2 <= len(options) <= 8:
        raise ValueError("advisory options must contain 2..8 choices")
    ids = []
    for option in options:
        if not isinstance(option, dict) or set(option) != {"id", "description"}:
            raise ValueError("advisory option shape mismatch")
        if not isinstance(option["id"], str) or not option["id"] or not isinstance(option["description"], str) or not option["description"].strip():
            raise ValueError("advisory option invalid")
        ids.append(option["id"])
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate advisory option id")
    return path, fixture


def validate_probabilities(option_ids: list[str], values: Any) -> dict[str, float]:
    if not isinstance(values, list) or len(values) != len(option_ids):
        raise ValueError("probability shape mismatch")
    probs = {}
    for option_id, value in zip(option_ids, values):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) or not 0.0 <= float(value) <= 1.0:
            raise ValueError("probabilities must be finite numbers in [0,1]")
        probs[option_id] = float(value)
    if not math.isclose(sum(probs.values()), 1.0, rel_tol=0.0, abs_tol=1e-5):
        raise ValueError("probabilities are not normalized")
    return probs


def select_option(probs: dict[str, float]) -> tuple[str | None, str]:
    best = max(probs.values())
    winners = [key for key, value in probs.items() if value == best]
    if len(winners) != 1:
        return None, "TIE"
    return winners[0], "SELECTED"


def upstreams() -> dict[str, Any]:
    data = load_json(UPSTREAMS)
    if data.get("schema") != "theseus.typed-decision-upstreams.v1":
        raise ValueError("upstream registry schema mismatch")
    return data["sources"]


def common_receipt(fixture_path: Path, fixture: dict[str, Any], candidate: str, probs: dict[str, float], selected: str | None, decision_status: str, raw_path: Path) -> dict[str, Any]:
    return {
        "schema": "theseus.quasi-jev-advisory-candidate.v1",
        "claim_scope": "ADVISORY_ONLY",
        "candidate": candidate,
        "fixture": {"id": fixture["id"], "path": fixture_path.relative_to(ROOT).as_posix(), "sha256": sha256_file(fixture_path)},
        "raw": {"path": raw_path.name, "sha256": sha256_file(raw_path)},
        "option_ids": [option["id"] for option in fixture["options"]],
        "probabilities": probs,
        "selected_option": selected,
        "decision_status": decision_status,
        "repository_sha": os.environ.get("GITHUB_SHA"),
        "run_id": os.environ.get("GITHUB_RUN_ID"),
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "acceptance_authority": False,
        "permission_authority": False,
        "verification_authority": False,
        "promotion_authority": False,
        "jev_equivalence_claim": False,
        "calibration_claim": False,
    }


def cmd_prepare_semif(args):
    _, fixture = safe_registered_fixture(args.fixture_id)
    row = {"id": fixture["id"], "state": fixture["state"], "question": fixture["question"], "options": fixture["options"]}
    write_jsonl(Path(args.out), [row])


def cmd_prepare_kev(args):
    _, fixture = safe_registered_fixture(args.fixture_id)
    write_json(Path(args.out), {
        "state": fixture["state"],
        "questions": [{"instr": fixture["question"], "options": [option["description"] for option in fixture["options"]], "label": 0}],
        "_theseus": {"label_semantics": "DUMMY_REQUIRED_BY_KEV_ENCODER_NOT_EXPECTED_TARGET", "option_ids": [option["id"] for option in fixture["options"]]},
    })


def validate_semif_runtime_package(path: Path, sources: dict[str, Any]) -> dict[str, Any]:
    value = load_json(path)
    if value.get("schema") != "theseus.typed-decision-package-consumer-receipt.v1":
        raise ValueError("SemIf runtime package receipt schema mismatch")
    if value.get("status") != "READY" or value.get("claim_scope") != "RUNTIME_PACKAGE_CONSUMPTION_ONLY":
        raise ValueError("SemIf runtime package is not READY")
    if value.get("acceptance_authority") is not False:
        raise ValueError("SemIf runtime package carries authority")
    if value.get("source_revision") != sources["semif"]["revision"]:
        raise ValueError("SemIf runtime package source revision mismatch")
    return value


def validate_semif_model(row: dict[str, Any], sources: dict[str, Any]) -> dict[str, Any]:
    model = row.get("model")
    if not isinstance(model, dict):
        raise ValueError("SemIf model metadata missing")
    gguf = model.get("gguf")
    if not isinstance(gguf, dict):
        raise ValueError("SemIf GGUF metadata missing")
    expected_file = sources["qwen3_0_6b_gguf"].get("file", "Qwen3-0.6B-Q8_0.gguf")
    checks = [
        model.get("source") == "Qwen/Qwen3-0.6B",
        model.get("revision") == sources["qwen3_0_6b_base"]["revision"],
        model.get("backend") == "llamacpp",
        gguf.get("file") == expected_file,
        gguf.get("sha256") == sources["qwen3_0_6b_gguf"]["sha256"],
    ]
    if not all(checks):
        raise ValueError("SemIf observed model identity mismatch")
    return model


def cmd_normalize_semif(args):
    fixture_path, fixture = safe_registered_fixture(args.fixture_id)
    rows = read_jsonl(Path(args.raw))
    if len(rows) != 1:
        raise ValueError("SemIf advisory output must contain exactly one row")
    row = rows[0]
    option_ids = [option["id"] for option in fixture["options"]]
    if row.get("id") != fixture["id"] or row.get("option_ids") != option_ids:
        raise ValueError("SemIf advisory identity/options mismatch")
    probs = validate_probabilities(option_ids, row.get("probabilities"))
    selected, status = select_option(probs)
    sources = upstreams()
    observed_model = validate_semif_model(row, sources)
    validate_semif_runtime_package(Path(args.runtime_package), sources)
    receipt = common_receipt(fixture_path, fixture, "semif_qwen3_0_6b_q8", probs, selected, status, Path(args.raw))
    receipt["model_identity"] = {
        "semif_source_revision": sources["semif"]["revision"],
        "base_revision": sources["qwen3_0_6b_base"]["revision"],
        "gguf_revision": sources["qwen3_0_6b_gguf"]["revision"],
        "gguf_sha256": sources["qwen3_0_6b_gguf"]["sha256"],
    }
    receipt["observed_model"] = observed_model
    receipt["probability_status"] = row.get("probability_status")
    receipt["runtime_package_receipt_sha256"] = sha256_file(Path(args.runtime_package))
    write_json(Path(args.out), receipt)


def cmd_normalize_kev(args):
    fixture_path, fixture = safe_registered_fixture(args.fixture_id)
    raw_path = Path(args.raw)
    raw = load_json(raw_path)
    option_ids = [option["id"] for option in fixture["options"]]
    raw_fixture = raw.get("fixture") or {}
    meta = raw_fixture.get("_theseus") or {}
    if meta.get("option_ids") != option_ids:
        raise ValueError("Kev advisory option identity mismatch")
    questions = raw_fixture.get("questions")
    if not isinstance(questions, list) or len(questions) != 1:
        raise ValueError("Kev advisory fixture shape mismatch")
    probs_rows = raw.get("probabilities")
    if not isinstance(probs_rows, list) or len(probs_rows) != 1:
        raise ValueError("Kev advisory output shape mismatch")
    probs = validate_probabilities(option_ids, probs_rows[0])
    selected, status = select_option(probs)
    sources = upstreams()
    expected_checkpoint = f"{sources['kev_0_8b']['repository'].removeprefix('https://huggingface.co/')}@{sources['kev_0_8b']['revision']}"
    checkpoint = raw.get("checkpoint") or {}
    if checkpoint.get("requested") != expected_checkpoint or checkpoint.get("base_revision") != sources["qwen3_5_0_8b_base"]["revision"]:
        raise ValueError("Kev model identity mismatch")
    receipt = common_receipt(fixture_path, fixture, "kev_0_8b", probs, selected, status, raw_path)
    receipt["model_identity"] = {
        "kev_source_revision": sources["kev"]["revision"],
        "checkpoint_revision": sources["kev_0_8b"]["revision"],
        "base_revision": sources["qwen3_5_0_8b_base"]["revision"],
    }
    receipt["runtime"] = raw.get("runtime")
    write_json(Path(args.out), receipt)


def load_candidate(path: Path, expected: str, fixture_id: str, option_ids: list[str]) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    value = load_json(path)
    if value.get("schema") != "theseus.quasi-jev-advisory-candidate.v1" or value.get("candidate") != expected:
        raise ValueError(f"invalid advisory candidate receipt: {expected}")
    if value.get("claim_scope") != "ADVISORY_ONLY":
        raise ValueError("candidate receipt claim scope mismatch")
    fixture = value.get("fixture") or {}
    if fixture.get("id") != fixture_id or value.get("option_ids") != option_ids:
        raise ValueError("candidate receipt fixture/options mismatch")
    for field in ("acceptance_authority", "permission_authority", "verification_authority", "promotion_authority"):
        if value.get(field) is not False:
            raise ValueError(f"candidate receipt carries authority: {field}")
    return value


def cmd_aggregate(args):
    fixture_path, fixture = safe_registered_fixture(args.fixture_id)
    option_ids = [option["id"] for option in fixture["options"]]
    candidates = {
        "semif_qwen3_0_6b_q8": load_candidate(Path(args.semif), "semif_qwen3_0_6b_q8", fixture["id"], option_ids),
        "kev_0_8b": load_candidate(Path(args.kev), "kev_0_8b", fixture["id"], option_ids),
    }
    present = {k: v for k, v in candidates.items() if v is not None}
    if len(present) < 2:
        council_state = "INCOMPLETE"
    elif any(v.get("selected_option") is None for v in present.values()):
        council_state = "INCOMPLETE"
    elif len({v["selected_option"] for v in present.values()}) == 1:
        council_state = "AGREE"
    else:
        council_state = "DISAGREE"
    receipt = {
        "schema": "theseus.quasi-jev-advisory-council.v1",
        "claim_scope": "ADVISORY_ONLY",
        "fixture": {"id": fixture["id"], "path": fixture_path.relative_to(ROOT).as_posix(), "sha256": sha256_file(fixture_path)},
        "council_state": council_state,
        "candidate_jobs": {
            "semif_qwen3_0_6b_q8": args.semif_job_status,
            "kev_0_8b": args.kev_job_status,
        },
        "candidates": {name: (None if value is None else {"selected_option": value["selected_option"], "decision_status": value["decision_status"], "probabilities": value["probabilities"], "receipt_sha256": sha256_file(Path(args.semif if name.startswith('semif') else args.kev))}) for name, value in candidates.items()},
        "consensus_grants_authority": False,
        "acceptance_authority": False,
        "permission_authority": False,
        "verification_authority": False,
        "promotion_authority": False,
        "next_action_authority": "ASSISTANT_OPERATOR_CONTRACT_ONLY",
        "non_claims": ["not Jev equivalence", "not calibration", "not correctness", "not permission", "not verification"],
    }
    write_json(Path(args.out), receipt)


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="command", required=True)
    for name, func in (("prepare-semif", cmd_prepare_semif), ("prepare-kev", cmd_prepare_kev)):
        sp = sub.add_parser(name); sp.add_argument("--fixture-id", required=True); sp.add_argument("--out", required=True); sp.set_defaults(func=func)
    sp = sub.add_parser("normalize-semif"); sp.add_argument("--fixture-id", required=True); sp.add_argument("--raw", required=True); sp.add_argument("--runtime-package", required=True); sp.add_argument("--out", required=True); sp.set_defaults(func=cmd_normalize_semif)
    sp = sub.add_parser("normalize-kev"); sp.add_argument("--fixture-id", required=True); sp.add_argument("--raw", required=True); sp.add_argument("--out", required=True); sp.set_defaults(func=cmd_normalize_kev)
    sp = sub.add_parser("aggregate"); sp.add_argument("--fixture-id", required=True); sp.add_argument("--semif", required=True); sp.add_argument("--kev", required=True); sp.add_argument("--semif-job-status", required=True); sp.add_argument("--kev-job-status", required=True); sp.add_argument("--out", required=True); sp.set_defaults(func=cmd_aggregate)
    args = p.parse_args()
    try:
        args.func(args)
    except ValueError as exc:
        raise SystemExit(str(exc))


if __name__ == "__main__":
    main()
