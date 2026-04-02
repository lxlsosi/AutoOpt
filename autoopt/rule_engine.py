from __future__ import annotations

from pathlib import Path
from typing import Any

from autoopt.models import DecisionRule, JobState


def _artifact_exists(project_root: str, relative_path: str) -> bool:
    return (Path(project_root) / relative_path).exists()


def _metric_value(state: JobState, name: str) -> float | None:
    if name in state.best_metric:
        return float(state.best_metric[name])
    if name in state.latest_metrics:
        return float(state.latest_metrics[name])
    return None


def rule_matches(rule: DecisionRule, state: JobState, project_root: str) -> bool:
    when: dict[str, Any] = rule.when
    if when.get("always") is True:
        return True

    missing_artifacts = when.get("missing_artifacts", [])
    if any(_artifact_exists(project_root, path) for path in missing_artifacts):
        return False

    present_artifacts = when.get("present_artifacts", [])
    if any(not _artifact_exists(project_root, path) for path in present_artifacts):
        return False

    best_metric_at_least = when.get("best_metric_at_least")
    if best_metric_at_least:
        value = _metric_value(state, best_metric_at_least["name"])
        if value is None or value < float(best_metric_at_least["target"]):
            return False

    best_metric_below = when.get("best_metric_below")
    if best_metric_below:
        value = _metric_value(state, best_metric_below["name"])
        if value is None or value >= float(best_metric_below["target"]):
            return False

    tool_attempts_lt = when.get("tool_attempts_lt")
    if tool_attempts_lt:
        count = int(state.attempts_by_tool.get(tool_attempts_lt["tool"], 0))
        if count >= int(tool_attempts_lt["count"]):
            return False

    tool_attempts_gte = when.get("tool_attempts_gte")
    if tool_attempts_gte:
        count = int(state.attempts_by_tool.get(tool_attempts_gte["tool"], 0))
        if count < int(tool_attempts_gte["count"]):
            return False

    phase_in = when.get("phase_in")
    if phase_in and state.phase not in phase_in:
        return False

    attempts_lt = when.get("attempts_lt")
    if attempts_lt is not None and state.attempts >= int(attempts_lt):
        return False

    attempts_gte = when.get("attempts_gte")
    if attempts_gte is not None and state.attempts < int(attempts_gte):
        return False

    approval_required = when.get("approval_required")
    if approval_required is not None and state.approval_required is not bool(approval_required):
        return False

    return True
