#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "fixtures/anyjev/hbr1"
SOURCE_MANIFEST = SOURCE_DIR / "manifest.json"
CLEF_REPOSITORY = "Cloudflare/clef"
CLEF_REVISION = "2f3de3dd85f379784083b0814d997ab627200f0c"
CLEF_LICENSE = "Apache-2.0"
SYSTEM_ONE_MODEL = "clef"
QUESTION_ID = "next_experiment"
POLICY_VERSION = "NONE"
THRESHOLD_VERSION = "NONE"


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
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def to_system_one_request(pack: dict[str, Any]) -> dict[str, Any]:
    criteria: dict[str, str] = {}
    for option in pack["options"]:
        criteria[option["id"]] = option["description"]
    return {
        "model": SYSTEM_ONE_MODEL,
        "state": pack["state"],
        "questions": {
            QUESTION_ID: {
                "type": "choice",
                "instructions": pack["question"],
                "criteria": criteria,
            }
        },
    }


def generate(out_dir: Path) -> dict[str, Any]:
    source_manifest = load_json(SOURCE_MANIFEST)
    entries = []
    for surface in source_manifest["surfaces"]:
        source_path = SOURCE_DIR / surface["model_input_path"]
        actual_sha = sha256_file(source_path)
        if actual_sha != surface["model_input_sha256"]:
            raise ValueError(f"HBR-1 surface drift: {surface['surface_id']}")
        pack = load_json(source_path)
        request = to_system_one_request(pack)
        request_name = f"{surface['surface_id'].lower()}.json"
        request_path = out_dir / request_name
        write_json(request_path, request)
        entries.append(
            {
                "surface_id": surface["surface_id"],
                "expected_semantics": surface["expected_semantics"],
                "source_path": surface["model_input_path"],
                "source_sha256": actual_sha,
                "request_path": request_name,
                "request_sha256": sha256_file(request_path),
            }
        )

    manifest = {
        "schema": "theseus.clef-hbr1-preflight.v1",
        "claim_scope": "SYSTEM_ONE_PROJECTION_PREFLIGHT_ONLY",
        "candidate": {
            "repository": CLEF_REPOSITORY,
            "revision": CLEF_REVISION,
            "license": CLEF_LICENSE,
            "system_one_model": SYSTEM_ONE_MODEL,
            "execution_route": "UNRESOLVED",
        },
        "source_manifest": SOURCE_MANIFEST.relative_to(ROOT).as_posix(),
        "policy_version": POLICY_VERSION,
        "threshold_version": THRESHOLD_VERSION,
        "outcome_escrow_in_candidate_input": False,
        "surfaces": entries,
        "acceptance_authority": False,
        "permission_authority": False,
        "verification_authority": False,
        "promotion_authority": False,
    }
    write_json(out_dir / "manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare deterministic Clef/System One HBR-1 request projections.")
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()
    generate(Path(args.out_dir))


if __name__ == "__main__":
    main()
