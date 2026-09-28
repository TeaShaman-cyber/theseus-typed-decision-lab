#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOURCE_FIXTURE = ROOT / "fixtures/advisory/math-mutation-routing-v1.json"
UPSTREAMS = ROOT / "config/upstreams.json"
EXPECTED_SOURCE_FIXTURE_SHA256 = "bd85a9af02a98c20e23860116479fad38701aaf2c6b46a821225767744e4921f"
HISTORICAL_TYPED_DECISION_SHA = "b5e6da5295b0ea182236ab2cdf9a0105bdf8f48f"
HISTORICAL_STATE_SHA256 = "8a364b07f8ab3d01fbc60c8a18ff984ebe712b086f64ad5cfbcf6bb776095a14"
EXPECTED_ANYJEV_REVISION = "10d5db91dda38dbde74c6abc1c075ce6463723d1"
EXPECTED_ANYJEV_OBSERVED_AT = "2026-09-28"
EXPECTED_BASE_MODEL_REVISION = "c1899de289a04d12100db370d81485cdf75e47ca"

SURFACES = (
    ("S0_ORIGINAL", "SAME", "s0-original.json"),
    ("S1_ORDER_PRESERVE", "SAME", "s1-order-preserve.json"),
    ("S2_FORMAT_PRESERVE", "SAME", "s2-format-preserve.json"),
    ("S3_SEMANTIC_CHANGE_CONTROL", "CHANGED", "s3-semantic-change.json"),
)


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


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def question_pack(fixture: dict[str, Any]) -> dict[str, Any]:
    return {
        "state": fixture["state"],
        "question": fixture["question"],
        "options": [
            {"id": option["id"], "description": option["description"]}
            for option in fixture["options"]
        ],
    }


def build_surfaces(source: dict[str, Any]) -> dict[str, dict[str, Any]]:
    s0 = question_pack(source)

    s1 = json.loads(json.dumps(s0))
    shift = 2
    s1["options"] = s1["options"][shift:] + s1["options"][:shift]

    s2 = json.loads(json.dumps(s0))
    lines = s2["state"].splitlines()
    s2["state"] = "\n".join(sorted(lines))

    s3 = json.loads(json.dumps(s0))
    old = "tool.REPO_SEARCH=state:REPROBE_REQUIRED;"
    new = "tool.REPO_SEARCH=state:UNAVAILABLE;"
    if s3["state"].count(old) != 1:
        raise ValueError("expected exactly one REPO_SEARCH availability marker")
    s3["state"] = s3["state"].replace(old, new, 1)

    return {
        "S0_ORIGINAL": s0,
        "S1_ORDER_PRESERVE": s1,
        "S2_FORMAT_PRESERVE": s2,
        "S3_SEMANTIC_CHANGE_CONTROL": s3,
    }


def pack_receipt(pack: dict[str, Any]) -> dict[str, str]:
    options = pack["options"]
    return {
        "state_sha256": sha256_text(pack["state"]),
        "question_sha256": sha256_text(pack["question"]),
        "option_set_sha256": sha256_bytes(canonical_bytes(options)),
        "question_pack_sha256": sha256_bytes(canonical_bytes(pack)),
    }


def generate(out_dir: Path) -> dict[str, Any]:
    if sha256_file(SOURCE_FIXTURE) != EXPECTED_SOURCE_FIXTURE_SHA256:
        raise ValueError("historical HBR-1 source fixture drift")

    source = load_json(SOURCE_FIXTURE)
    if source.get("id") != "math-mutation-routing-v1":
        raise ValueError("unexpected HBR-1 source fixture identity")
    if sha256_text(source["state"]) != HISTORICAL_STATE_SHA256:
        raise ValueError("historical HBR-1 state drift")

    upstreams = load_json(UPSTREAMS)["sources"]
    anyjev = upstreams["anyjev"]
    base = upstreams["qwen3_0_6b_base"]
    if anyjev["revision"] != EXPECTED_ANYJEV_REVISION:
        raise ValueError("AnyJev revision drift")
    if anyjev.get("observed_at") != EXPECTED_ANYJEV_OBSERVED_AT:
        raise ValueError("AnyJev observation date drift")
    if base["revision"] != EXPECTED_BASE_MODEL_REVISION:
        raise ValueError("HBR-1 base model revision drift")

    surfaces = build_surfaces(source)
    entries = []
    filenames = {surface_id: filename for surface_id, _, filename in SURFACES}
    semantics = {surface_id: expected for surface_id, expected, _ in SURFACES}

    for surface_id, pack in surfaces.items():
        path = out_dir / filenames[surface_id]
        write_json(path, pack)
        entries.append(
            {
                "surface_id": surface_id,
                "expected_semantics": semantics[surface_id],
                "model_input_path": filenames[surface_id],
                "model_input_sha256": sha256_file(path),
                **pack_receipt(pack),
            }
        )

    manifest = {
        "schema": "theseus.anyjev-hbr1-manifest.v1",
        "claim_scope": "ADVISORY_HISTORICAL_BLIND_REPLAY_ONLY",
        "source": {
            "fixture_id": source["id"],
            "fixture_path": SOURCE_FIXTURE.relative_to(ROOT).as_posix(),
            "fixture_sha256": EXPECTED_SOURCE_FIXTURE_SHA256,
            "historical_repository_sha": HISTORICAL_TYPED_DECISION_SHA,
            "historical_state_sha256": HISTORICAL_STATE_SHA256,
        },
        "candidate": {
            "anyjev_repository": anyjev["repository"],
            "anyjev_revision": anyjev["revision"],
            "anyjev_package_version": anyjev["package_version"],
            "anyjev_observed_at": anyjev["observed_at"],
            "anyjev_license": anyjev["license"],
            "base_model_repository": base["repository"],
            "base_model_revision": base["revision"],
            "base_model_license": base["license"],
            "levels": ["raw", "L0"],
        },
        "transforms": {
            "S0_ORIGINAL": "identity",
            "S1_ORDER_PRESERVE": "cyclic option rotation by 2; option text unchanged",
            "S2_FORMAT_PRESERVE": "lexicographic reorder of complete state lines; line text unchanged",
            "S3_SEMANTIC_CHANGE_CONTROL": "REPO_SEARCH availability REPROBE_REQUIRED -> UNAVAILABLE; all other text unchanged",
        },
        "surfaces": entries,
        "outcome_escrow_in_candidate_input": False,
        "needle_role": "BOUNDED_COMPARISON_WITNESS_NOT_SEMANTIC_ORACLE",
        "acceptance_authority": False,
        "permission_authority": False,
        "verification_authority": False,
        "promotion_authority": False,
    }
    write_json(out_dir / "manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare deterministic AnyJev HBR-1 blind-replay surfaces.")
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()
    generate(Path(args.out_dir))


if __name__ == "__main__":
    main()
