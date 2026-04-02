from __future__ import annotations

import json
import subprocess
from pathlib import Path

from autoopt.models import JobState, ToolExecutionOutcome, ToolSpec


class ShellAdapter:
    def __init__(self, role: str) -> None:
        self.role = role

    def run(
        self,
        tool: ToolSpec,
        project_root: str,
        state: JobState,
        state_path: str,
        result_json_path: str,
    ) -> ToolExecutionOutcome:
        context = {
            "project_root": project_root,
            "state_path": state_path,
            "result_json": result_json_path,
            "tool_name": tool.name,
            "job_id": state.job_id,
        }
        command = tool.command.format(**context)
        completed = subprocess.run(
            command,
            shell=True,
            cwd=project_root,
            capture_output=True,
            text=True,
        )

        result_path = Path(result_json_path)
        result_data = {}
        if result_path.exists():
            result_data = json.loads(result_path.read_text(encoding="utf-8"))

        if completed.returncode != 0:
            summary = result_data.get("summary") or completed.stderr.strip() or f"{tool.name} failed"
            return ToolExecutionOutcome(
                tool_name=tool.name,
                success=False,
                summary=summary,
                exit_code=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
                budget_cost=tool.budget_cost,
            )

        summary = result_data.get("summary") or completed.stdout.strip() or f"{tool.name} finished"
        return ToolExecutionOutcome(
            tool_name=tool.name,
            success=bool(result_data.get("success", True)),
            summary=summary,
            artifacts=result_data.get("artifacts", {}),
            metrics=result_data.get("metrics", {}),
            dataset_version=result_data.get("dataset_version"),
            eval_suite_version=result_data.get("eval_suite_version"),
            gpu_job_id=result_data.get("gpu_job_id"),
            hypotheses=result_data.get("hypotheses", []),
            notes=result_data.get("notes", []),
            budget_cost=float(result_data.get("budget_cost", tool.budget_cost)),
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )


class AdapterRegistry:
    def __init__(self) -> None:
        self.adapters = {
            "data": ShellAdapter("data"),
            "compute": ShellAdapter("compute"),
            "evaluation": ShellAdapter("evaluation"),
        }

    def run_tool(
        self,
        tool: ToolSpec,
        project_root: str,
        state: JobState,
        state_path: str,
        result_json_path: str,
    ) -> ToolExecutionOutcome:
        adapter = self.adapters.get(tool.adapter)
        if adapter is None:
            raise ValueError(f"Unknown adapter '{tool.adapter}' for tool '{tool.name}'")
        return adapter.run(tool, project_root, state, state_path, result_json_path)
