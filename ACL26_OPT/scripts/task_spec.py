from __future__ import annotations

import json
from pathlib import Path


def load_task_definition(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def dataset_policy_map(task_definition: dict) -> dict[str, dict]:
    policy = task_definition.get("dataset_policy", {})
    merged: dict[str, dict] = {}
    for bucket in ["whitelist", "graylist", "blocked"]:
        for item in policy.get(bucket, []):
            merged[item["name"]] = {
                **item,
                "policy_bucket": bucket,
            }
    return merged


def label_space(task_definition: dict) -> list[str]:
    return list(task_definition.get("label_space", []))


def region_mapping(task_definition: dict, mapping_name: str) -> dict[str, str]:
    return dict(task_definition.get("region_mapping", {}).get(mapping_name, {}))
