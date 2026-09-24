#!/usr/bin/env python3
from pathlib import Path

import yaml
from yaml.constructor import ConstructorError
from yaml.resolver import BaseResolver

ROOT = Path(__file__).resolve().parents[1]


class UniqueKeyLoader(yaml.SafeLoader):
    pass


def construct_unique_mapping(loader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError as exc:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"unhashable mapping key: {key!r}",
                key_node.start_mark,
            ) from exc
        if duplicate:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"duplicate mapping key: {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(
    BaseResolver.DEFAULT_MAPPING_TAG,
    construct_unique_mapping,
)


def workflow_paths(root: Path):
    directory = root / ".github" / "workflows"
    return sorted(set(directory.glob("*.yml")) | set(directory.glob("*.yaml")))


def validate_workflows(root: Path) -> int:
    paths = workflow_paths(root)
    if not paths:
        raise SystemExit("no workflow YAML files found")
    for path in paths:
        try:
            yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueKeyLoader)
        except Exception as exc:
            raise SystemExit(
                f"WORKFLOW_YAML_INVALID: {path.relative_to(root)}: {exc}"
            )
    return len(paths)


def main() -> None:
    count = validate_workflows(ROOT)
    print(f"WORKFLOW_YAML_PASS files={count}")


if __name__ == "__main__":
    main()
