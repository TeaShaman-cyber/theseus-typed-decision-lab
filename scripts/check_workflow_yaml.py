#!/usr/bin/env python3
from pathlib import Path
import sys
import yaml

ROOT = Path(__file__).resolve().parents[1]
paths = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
if not paths:
    raise SystemExit("no workflow YAML files found")

for path in paths:
    try:
        yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SystemExit(f"WORKFLOW_YAML_INVALID: {path.relative_to(ROOT)}: {exc}")

print(f"WORKFLOW_YAML_PASS files={len(paths)}")
