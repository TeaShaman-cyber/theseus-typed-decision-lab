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


def _sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def build_question_custody(
    fixture_path: Path,
    fixture: dict[str, Any],
    *,
    repository_sha: str,
) -> dict[str, Any]:
    if not isinstance(repository_sha, str) or not repository_sha:
        raise ValueError("repository SHA required for question custody")
    options = [
        {"id": option["id"], "description": option["description"]}
        for option in fixture["options"]
    ]
    question_pack = {
        "state": fixture["state"],
        "question": fixture["question"],
        "options": options,
    }
    return {
        "schema": "theseus.quasi-jev-question-custody.v1",
        "claim_scope": "ADVISORY_QUESTION_BINDING_ONLY",
        "method": "REGISTERED_FIXTURE_SHA256_V1",
        "bound_before_scoring": True,
        "repository_sha": repository_sha,
        "fixture_id": fixture["id"],
        "fixture_path": fixture_path.relative_to(ROOT).as_posix(),
        "fixture_sha256": sha256_file(fixture_path),
        "state_sha256": _sha256_text(fixture["state"]),
        "question_sha256": _sha256_text(fixture["question"]),
        "option_set_sha256": sha256_bytes(canonical_bytes(options)),
        "question_pack_sha256": sha256_bytes(canonical_bytes(question_pack)),
        "policy_version": "NONE",
        "threshold_version": "NONE",
        "acceptance_authority": False,
        "permission_authority": False,
        "promotion_authority": False,
    }


def distribution_metrics(probs: dict[str, float]) -> dict[str, Any]:
    values = [float(value) for value in probs.values()]
    if len(values) < 2:
        raise ValueError("distribution metrics require at least two options")
    total = math.fsum(values)
    if total <= 0.0:
        raise ValueError("distribution metrics require positive probability mass")
    ordered = sorted((value / total for value in values), reverse=True)
    entropy = -math.fsum(value * math.log(value) for value in ordered if value > 0.0)
    return {
        "method": "SHANNON_NATS_AND_TOP1_TOP2_MARGIN_V1",
        "entropy_nats": round(entropy, 15),
        "top1_top2_margin": round(ordered[0] - ordered[1], 15),
    }


def cmd_prepare_custody(args):
    fixture_path, fixture = safe_registered_fixture(args.fixture_id)
    repository_sha = os.environ.get("GITHUB_SHA")
    if not repository_sha:
        raise ValueError("GITHUB_SHA required for pre-scoring question custody")
    write_json(
        Path(args.out),
        build_question_custody(
            fixture_path,
            fixture,
            repository_sha=repository_sha,
        ),
    )


def validate_question_custody(
    path: Path,
    fixture_path: Path,
    fixture: dict[str, Any],
) -> dict[str, Any]:
    value = load_json(path)
    repository_sha = value.get("repository_sha")
    expected = build_question_custody(
        fixture_path,
        fixture,
        repository_sha=repository_sha,
    )
    if value != expected:
        raise ValueError("question custody does not match registered fixture")
    current_sha = os.environ.get("GITHUB_SHA")
    if current_sha and repository_sha != current_sha:
        raise ValueError("question custody repository SHA mismatch")
    return value


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


def validate_probability_map(option_ids: list[str], values: Any) -> dict[str, float]:
    if not isinstance(values, dict) or set(values) != set(option_ids):
        raise ValueError("probability map option identity mismatch")
    probs = {}
    for option_id in option_ids:
        value = values[option_id]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) or not 0.0 <= float(value) <= 1.0:
            raise ValueError("probabilities must be finite numbers in [0,1]")
        probs[option_id] = float(value)
    if not math.isclose(sum(probs.values()), 1.0, rel_tol=0.0, abs_tol=2e-4):
        raise ValueError("probability map is not normalized")
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


def common_receipt(
    fixture_path: Path,
    fixture: dict[str, Any],
    candidate: str,
    probs: dict[str, float],
    selected: str | None,
    decision_status: str,
    raw_path: Path,
    custody: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema": "theseus.quasi-jev-advisory-candidate.v1",
        "claim_scope": "ADVISORY_ONLY",
        "candidate": candidate,
        "fixture": {"id": fixture["id"], "path": fixture_path.relative_to(ROOT).as_posix(), "sha256": sha256_file(fixture_path)},
        "raw": {"path": raw_path.name, "sha256": sha256_file(raw_path)},
        "option_ids": [option["id"] for option in fixture["options"]],
        "probabilities": probs,
        "distribution_metrics": distribution_metrics(probs),
        "question_custody": custody,
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


def kev_projection(fixture: dict[str, Any]) -> dict[str, Any]:
    return {
        "state": fixture["state"],
        "questions": [{
            "instr": fixture["question"],
            "options": [option["description"] for option in fixture["options"]],
            "label": 0,
        }],
        "_theseus": {
            "label_semantics": "DUMMY_REQUIRED_BY_KEV_ENCODER_NOT_EXPECTED_TARGET",
            "option_ids": [option["id"] for option in fixture["options"]],
        },
    }


def cmd_prepare_kev(args):
    _, fixture = safe_registered_fixture(args.fixture_id)
    write_json(Path(args.out), kev_projection(fixture))


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
    custody = validate_question_custody(Path(args.custody), fixture_path, fixture)
    receipt = common_receipt(
        fixture_path, fixture, "semif_qwen3_0_6b_q8",
        probs, selected, status, Path(args.raw), custody,
    )
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
    raw_fixture = raw.get("fixture")
    expected_fixture = kev_projection(fixture)
    if not isinstance(raw_fixture, dict) or canonical_bytes(raw_fixture) != canonical_bytes(expected_fixture):
        raise ValueError("Kev embedded fixture does not match registered projection")
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
    custody = validate_question_custody(Path(args.custody), fixture_path, fixture)
    receipt = common_receipt(
        fixture_path, fixture, "kev_0_8b",
        probs, selected, status, raw_path, custody,
    )
    receipt["model_identity"] = {
        "kev_source_revision": sources["kev"]["revision"],
        "checkpoint_revision": sources["kev_0_8b"]["revision"],
        "base_revision": sources["qwen3_5_0_8b_base"]["revision"],
    }
    receipt["runtime"] = raw.get("runtime")
    write_json(Path(args.out), receipt)


def cmd_normalize_von(args):
    fixture_path, fixture = safe_registered_fixture(args.fixture_id)
    raw_path = Path(args.raw)
    raw = load_json(raw_path)
    if raw.get("schema") != "theseus.von-cpu-feasibility.v1":
        raise ValueError("Von raw receipt schema mismatch")
    if raw.get("claim_scope") != "RUNTIME_FEASIBILITY_ONLY" or raw.get("classification") != "CPU_FEASIBLE":
        raise ValueError("Von raw receipt is not CPU_FEASIBLE")
    for field in ("acceptance_authority", "permission_authority", "verification_authority", "promotion_authority"):
        if raw.get(field) is not False:
            raise ValueError(f"Von raw receipt carries authority: {field}")

    custody = validate_question_custody(Path(args.custody), fixture_path, fixture)
    if raw.get("repository_sha") != custody.get("repository_sha"):
        raise ValueError("Von raw repository SHA does not match question custody")

    sources = upstreams()
    identity = raw.get("identity") or {}
    if identity.get("source_repo") != "wfzyx/von" or identity.get("source_revision") != sources["von"]["revision"]:
        raise ValueError("Von source identity mismatch")
    source_install = identity.get("source_install") or {}
    if source_install.get("commit_id") != sources["von"]["revision"]:
        raise ValueError("Von installed source revision mismatch")
    if identity.get("model_repo") != "wfzyx/von" or identity.get("model_revision") != sources["von_model"]["revision"]:
        raise ValueError("Von model identity mismatch")
    snapshot = identity.get("model_snapshot") or {}
    if snapshot.get("manifest_sha256") != sources["von_model"].get("snapshot_manifest_sha256"):
        raise ValueError("Von model snapshot manifest mismatch")

    raw_fixture = raw.get("fixture") or {}
    if raw_fixture.get("id") != fixture["id"] or raw_fixture.get("sha256") != sha256_file(fixture_path):
        raise ValueError("Von embedded fixture identity mismatch")
    if raw_fixture.get("question_pack_sha256") != custody.get("question_pack_sha256"):
        raise ValueError("Von question pack does not match pre-scoring custody")

    runtime = raw.get("runtime") or {}
    if runtime.get("hf_hub_offline") is not True or runtime.get("transformers_offline") is not True:
        raise ValueError("Von advisory inference was not offline after pinned snapshot")

    calibration = raw.get("calibration") or {}
    artifact = calibration.get("artifact") or {}
    if calibration.get("status") != "CALIBRATED":
        raise ValueError("Von pinned candidate calibration not active")
    if artifact.get("sha256") != sources["von_model"].get("calibration_sha256"):
        raise ValueError("Von calibration artifact mismatch")

    original = ((raw.get("observations") or {}).get("original") or {})
    option_ids = [option["id"] for option in fixture["options"]]
    probs = validate_probability_map(option_ids, original.get("probabilities"))
    selected, status = select_option(probs)
    reported_choice = original.get("choice")
    if selected is None:
        best = max(probs.values())
        tied_maxima = {key for key, value in probs.items() if value == best}
        if reported_choice not in tied_maxima:
            raise ValueError("Von selected option is not among tied probability maxima")
    elif reported_choice != selected:
        raise ValueError("Von selected option does not match preserved distribution")

    reported_confidence = original.get("reported_confidence")
    if isinstance(reported_confidence, bool) or not isinstance(reported_confidence, (int, float)) or not math.isfinite(float(reported_confidence)):
        raise ValueError("Von reported confidence invalid")

    receipt = common_receipt(
        fixture_path, fixture, "von_1_2_0",
        probs, selected, status, raw_path, custody,
    )
    receipt["model_identity"] = {
        "source_revision": sources["von"]["revision"],
        "model_revision": sources["von_model"]["revision"],
        "snapshot_manifest_sha256": snapshot["manifest_sha256"],
    }
    receipt["calibration"] = calibration
    receipt["reported_confidence"] = float(reported_confidence)
    receipt["runtime"] = runtime
    receipt["raw_stability"] = (raw.get("observations") or {}).get("stability")
    write_json(Path(args.out), receipt)


def pairwise_agreement(candidates: dict[str, dict[str, Any] | None]) -> dict[str, bool | None]:
    names = list(candidates)
    result = {}
    for index, left in enumerate(names):
        for right in names[index + 1:]:
            a = candidates[left]
            b = candidates[right]
            key = f"{left}__{right}"
            if a is None or b is None or a.get("selected_option") is None or b.get("selected_option") is None:
                result[key] = None
            else:
                result[key] = a["selected_option"] == b["selected_option"]
    return result


def load_candidate(
    path: Path,
    expected: str,
    fixture_path: Path,
    fixture: dict[str, Any],
    option_ids: list[str],
) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    value = load_json(path)
    if value.get("schema") != "theseus.quasi-jev-advisory-candidate.v1" or value.get("candidate") != expected:
        raise ValueError(f"invalid advisory candidate receipt: {expected}")
    if value.get("claim_scope") != "ADVISORY_ONLY":
        raise ValueError("candidate receipt claim scope mismatch")
    candidate_fixture = value.get("fixture") or {}
    if candidate_fixture.get("id") != fixture["id"] or value.get("option_ids") != option_ids:
        raise ValueError("candidate receipt fixture/options mismatch")
    custody = value.get("question_custody")
    if not isinstance(custody, dict):
        raise ValueError("candidate receipt question custody missing")
    expected_custody = build_question_custody(
        fixture_path,
        fixture,
        repository_sha=custody.get("repository_sha"),
    )
    if custody != expected_custody:
        raise ValueError("candidate receipt question custody mismatch")
    current_sha = os.environ.get("GITHUB_SHA")
    if current_sha and custody.get("repository_sha") != current_sha:
        raise ValueError("candidate receipt repository SHA mismatch")
    probs = validate_probability_map(option_ids, value.get("probabilities"))
    metrics = value.get("distribution_metrics")
    if metrics != distribution_metrics(probs):
        raise ValueError("candidate receipt distribution metrics mismatch")
    for field in ("acceptance_authority", "permission_authority", "verification_authority", "promotion_authority"):
        if value.get(field) is not False:
            raise ValueError(f"candidate receipt carries authority: {field}")
    return value


def cmd_aggregate(args):
    fixture_path, fixture = safe_registered_fixture(args.fixture_id)
    option_ids = [option["id"] for option in fixture["options"]]
    candidates = {
        "semif_qwen3_0_6b_q8": load_candidate(
            Path(args.semif), "semif_qwen3_0_6b_q8", fixture_path, fixture, option_ids
        ),
        "kev_0_8b": load_candidate(
            Path(args.kev), "kev_0_8b", fixture_path, fixture, option_ids
        ),
        "von_1_2_0": load_candidate(
            Path(getattr(args, "von", "")), "von_1_2_0", fixture_path, fixture, option_ids
        ),
    }
    present = {k: v for k, v in candidates.items() if v is not None}
    if len(present) == 3:
        availability = "COMPLETE"
    elif len(present) >= 2:
        availability = "DEGRADED"
    else:
        availability = "INCOMPLETE"
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
        "availability": availability,
        "candidate_jobs": {
            "semif_qwen3_0_6b_q8": args.semif_job_status,
            "kev_0_8b": args.kev_job_status,
            "von_1_2_0": getattr(args, "von_job_status", "not_configured"),
        },
        "pairwise_agreement": pairwise_agreement(candidates),
        "three_way_agreement": (
            len(present) == 3
            and all(v.get("selected_option") is not None for v in present.values())
            and len({v["selected_option"] for v in present.values()}) == 1
        ) if len(present) == 3 else None,
        "question_custody": (
            next(iter(present.values()))["question_custody"] if present else None
        ),
        "candidates": {
            name: (
                None
                if value is None
                else {
                    "selected_option": value["selected_option"],
                    "decision_status": value["decision_status"],
                    "probabilities": value["probabilities"],
                    "distribution_metrics": value["distribution_metrics"],
                    "receipt_sha256": sha256_file(
                        Path(
                            args.semif
                            if name.startswith("semif")
                            else args.kev
                            if name.startswith("kev")
                            else getattr(args, "von")
                        )
                    ),
                }
            )
            for name, value in candidates.items()
        },
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
    for name, func in (("prepare-semif", cmd_prepare_semif), ("prepare-kev", cmd_prepare_kev), ("prepare-custody", cmd_prepare_custody)):
        sp = sub.add_parser(name); sp.add_argument("--fixture-id", required=True); sp.add_argument("--out", required=True); sp.set_defaults(func=func)
    sp = sub.add_parser("normalize-semif"); sp.add_argument("--fixture-id", required=True); sp.add_argument("--raw", required=True); sp.add_argument("--runtime-package", required=True); sp.add_argument("--custody", required=True); sp.add_argument("--out", required=True); sp.set_defaults(func=cmd_normalize_semif)
    sp = sub.add_parser("normalize-kev"); sp.add_argument("--fixture-id", required=True); sp.add_argument("--raw", required=True); sp.add_argument("--custody", required=True); sp.add_argument("--out", required=True); sp.set_defaults(func=cmd_normalize_kev)
    sp = sub.add_parser("normalize-von"); sp.add_argument("--fixture-id", required=True); sp.add_argument("--raw", required=True); sp.add_argument("--custody", required=True); sp.add_argument("--out", required=True); sp.set_defaults(func=cmd_normalize_von)
    sp = sub.add_parser("aggregate"); sp.add_argument("--fixture-id", required=True); sp.add_argument("--semif", required=True); sp.add_argument("--kev", required=True); sp.add_argument("--von", required=True); sp.add_argument("--semif-job-status", required=True); sp.add_argument("--kev-job-status", required=True); sp.add_argument("--von-job-status", required=True); sp.add_argument("--out", required=True); sp.set_defaults(func=cmd_aggregate)
    args = p.parse_args()
    try:
        args.func(args)
    except ValueError as exc:
        raise SystemExit(str(exc))


if __name__ == "__main__":
    main()
