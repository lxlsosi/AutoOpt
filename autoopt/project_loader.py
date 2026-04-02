from __future__ import annotations

import json
from pathlib import Path

from autoopt.models import DecisionRule, ProjectContract, ProjectSpec, ToolSpec


def load_project(project_path: str) -> tuple[ProjectSpec, ProjectContract, str]:
    project_file = Path(project_path).resolve()
    project_root = project_file.parent
    data = json.loads(project_file.read_text(encoding="utf-8"))

    walkthrough_path = (project_root / data["walkthrough_path"]).resolve()
    contract_path = (project_root / data["contract_path"]).resolve()

    contract = ProjectContract.from_dict(json.loads(contract_path.read_text(encoding="utf-8")))
    tool_registry = {
        name: ToolSpec.from_dict(name, tool_data)
        for name, tool_data in data.get("tool_registry", {}).items()
    }
    decision_rules = [DecisionRule.from_dict(rule) for rule in data.get("decision_rules", [])]

    known = {
        "project_id",
        "name",
        "walkthrough_path",
        "contract_path",
        "runtime",
        "tool_registry",
        "decision_rules",
    }
    metadata = {key: value for key, value in data.items() if key not in known}

    spec = ProjectSpec(
        project_id=data["project_id"],
        name=data["name"],
        project_root=str(project_root),
        walkthrough_path=str(walkthrough_path),
        contract_path=str(contract_path),
        runtime=data.get("runtime", {}),
        tool_registry=tool_registry,
        decision_rules=decision_rules,
        metadata=metadata,
    )
    walkthrough_text = walkthrough_path.read_text(encoding="utf-8")
    return spec, contract, walkthrough_text
