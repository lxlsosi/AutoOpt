from __future__ import annotations

import json
import os
import subprocess
from pathlib import PurePosixPath
from pathlib import Path

from autoopt.models import JobState, ProjectSpec, ToolExecutionOutcome, ToolSpec
from autoopt.remote import SSHRemoteManager
from autoopt.routing import ExecutionRouter


class ShellAdapter:
    def __init__(self, role: str) -> None:
        self.role = role

    def run(
        self,
        tool: ToolSpec,
        spec: ProjectSpec,
        project_root: str,
        state: JobState,
        state_path: str,
        result_json_path: str,
        execution_plan,
    ) -> ToolExecutionOutcome:
        if execution_plan.mode == "dispatch":
            return self._run_dispatch(tool, spec, project_root, state, state_path, result_json_path, execution_plan)

        context = {
            "project_root": execution_plan.execution_project_root,
            "orchestrator_project_root": project_root,
            "state_path": state_path,
            "result_json": result_json_path,
            "tool_name": tool.name,
            "job_id": state.job_id,
            "execution_host": execution_plan.host_name,
            "execution_mode": execution_plan.mode,
            "execution_project_root": execution_plan.execution_project_root,
            "ssh_target": execution_plan.ssh_target or "",
            "dispatch_reason": execution_plan.reason,
            "controller_host": spec.execution_topology.controller_host or "",
        }
        command = tool.command.format(**context)
        env = os.environ.copy()
        env.update(
            {
                "AUTOOPT_EXECUTION_HOST": execution_plan.host_name,
                "AUTOOPT_EXECUTION_MODE": execution_plan.mode,
                "AUTOOPT_EXECUTION_PROJECT_ROOT": execution_plan.execution_project_root,
                "AUTOOPT_CONTROLLER_HOST": spec.execution_topology.controller_host or "",
                "AUTOOPT_SSH_TARGET": execution_plan.ssh_target or "",
                "AUTOOPT_DISPATCH_REASON": execution_plan.reason,
            }
        )
        completed = subprocess.run(
            command,
            shell=True,
            cwd=project_root,
            capture_output=True,
            text=True,
            env=env,
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
                execution_host=result_data.get("execution_host", execution_plan.host_name),
                execution_mode=result_data.get("execution_mode", execution_plan.mode),
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
            execution_host=result_data.get("execution_host", execution_plan.host_name),
            execution_mode=result_data.get("execution_mode", execution_plan.mode),
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )

    def _run_dispatch(
        self,
        tool: ToolSpec,
        spec: ProjectSpec,
        project_root: str,
        state: JobState,
        state_path: str,
        result_json_path: str,
        execution_plan,
    ) -> ToolExecutionOutcome:
        if tool.adapter == "compute":
            return self._run_dispatch_compute(tool, spec, project_root, state, state_path, result_json_path, execution_plan)

        remote_manager = SSHRemoteManager(spec)
        bootstrap = remote_manager.bootstrap_host(execution_plan.host_name)

        state_relative = Path(state_path).resolve().relative_to(Path(project_root).resolve())
        result_relative = Path(result_json_path).resolve().relative_to(Path(project_root).resolve())
        remote_state_path = str(PurePosixPath(bootstrap.remote_project_root) / PurePosixPath(state_relative.as_posix()))
        remote_result_path = str(PurePosixPath(bootstrap.remote_project_root) / PurePosixPath(result_relative.as_posix()))

        context = {
            "project_root": bootstrap.remote_project_root,
            "orchestrator_project_root": project_root,
            "state_path": remote_state_path,
            "result_json": remote_result_path,
            "tool_name": tool.name,
            "job_id": state.job_id,
            "execution_host": execution_plan.host_name,
            "execution_mode": execution_plan.mode,
            "execution_project_root": bootstrap.remote_project_root,
            "ssh_target": execution_plan.ssh_target or "",
            "dispatch_reason": execution_plan.reason,
            "controller_host": spec.execution_topology.controller_host or "",
        }
        command = tool.command.format(**context)
        completed = remote_manager.dispatch_tool(
            bootstrap=bootstrap,
            tool=tool,
            remote_command=command,
            local_result_json_path=result_json_path,
            remote_result_json_path=remote_result_path,
            state_path=state_path,
            remote_state_path=remote_state_path,
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
                budget_cost=float(result_data.get("budget_cost", tool.budget_cost)),
                execution_host=result_data.get("execution_host", execution_plan.host_name),
                execution_mode=result_data.get("execution_mode", execution_plan.mode),
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
            execution_host=result_data.get("execution_host", execution_plan.host_name),
            execution_mode=result_data.get("execution_mode", execution_plan.mode),
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )

    def _run_dispatch_compute(
        self,
        tool: ToolSpec,
        spec: ProjectSpec,
        project_root: str,
        state: JobState,
        state_path: str,
        result_json_path: str,
        execution_plan,
    ) -> ToolExecutionOutcome:
        remote_manager = SSHRemoteManager(spec)
        existing_job = state.pending_jobs.get(tool.name)
        if existing_job:
            polled = remote_manager.poll_background_job(existing_job)
            log_artifacts = remote_manager.sync_job_logs(existing_job)
            status = polled.get("status", "unknown")

            if status == "running":
                return ToolExecutionOutcome(
                    tool_name=tool.name,
                    success=True,
                    summary=f"Remote job '{existing_job['job_name']}' is still running on {existing_job['host_name']}.",
                    artifacts=log_artifacts,
                    execution_host=existing_job["host_name"],
                    execution_mode="dispatch",
                    deferred=True,
                    count_attempt=False,
                    pending_job=existing_job,
                    notes=[
                        f"Polling remote job '{existing_job['job_name']}' on {existing_job['host_name']}.",
                    ],
                )

            result_data = remote_manager.collect_job_outputs(existing_job, tool)
            summary = result_data.get("summary")
            if not summary:
                if status == "completed":
                    summary = f"Remote job '{existing_job['job_name']}' completed on {existing_job['host_name']}."
                else:
                    summary = f"Remote job '{existing_job['job_name']}' failed on {existing_job['host_name']}."

            return ToolExecutionOutcome(
                tool_name=tool.name,
                success=status == "completed" and bool(result_data.get("success", True)),
                summary=summary,
                artifacts={**log_artifacts, **result_data.get("artifacts", {})},
                metrics=result_data.get("metrics", {}),
                dataset_version=result_data.get("dataset_version"),
                eval_suite_version=result_data.get("eval_suite_version"),
                gpu_job_id=result_data.get("gpu_job_id") or existing_job["job_name"],
                hypotheses=result_data.get("hypotheses", []),
                notes=result_data.get("notes", []),
                budget_cost=float(result_data.get("budget_cost", tool.budget_cost if status == "completed" else 0.0)),
                execution_host=result_data.get("execution_host", existing_job["host_name"]),
                execution_mode=result_data.get("execution_mode", "dispatch"),
                count_attempt=False,
                clear_pending_job=True,
            )

        bootstrap = remote_manager.bootstrap_host(execution_plan.host_name)
        state_relative = Path(state_path).resolve().relative_to(Path(project_root).resolve())
        result_relative = Path(result_json_path).resolve().relative_to(Path(project_root).resolve())
        remote_state_path = str(PurePosixPath(bootstrap.remote_project_root) / PurePosixPath(state_relative.as_posix()))
        remote_result_path = str(PurePosixPath(bootstrap.remote_project_root) / PurePosixPath(result_relative.as_posix()))

        context = {
            "project_root": bootstrap.remote_project_root,
            "orchestrator_project_root": project_root,
            "state_path": remote_state_path,
            "result_json": remote_result_path,
            "tool_name": tool.name,
            "job_id": state.job_id,
            "execution_host": execution_plan.host_name,
            "execution_mode": execution_plan.mode,
            "execution_project_root": bootstrap.remote_project_root,
            "ssh_target": execution_plan.ssh_target or "",
            "dispatch_reason": execution_plan.reason,
            "controller_host": spec.execution_topology.controller_host or "",
        }
        command = tool.command.format(**context)
        pending_job = remote_manager.submit_background_tool(
            bootstrap=bootstrap,
            tool=tool,
            remote_command=command,
            local_result_json_path=result_json_path,
            remote_result_json_path=remote_result_path,
            state_path=state_path,
            remote_state_path=remote_state_path,
        )
        log_artifacts = remote_manager.sync_job_logs(pending_job)
        return ToolExecutionOutcome(
            tool_name=tool.name,
            success=True,
            summary=f"Submitted remote job '{pending_job['job_name']}' to {execution_plan.host_name}.",
            artifacts=log_artifacts,
            gpu_job_id=pending_job["job_name"],
            execution_host=execution_plan.host_name,
            execution_mode=execution_plan.mode,
            deferred=True,
            count_attempt=True,
            pending_job=pending_job,
            notes=[
                f"Background training job submitted to {execution_plan.host_name}.",
                f"tmux session: {pending_job['remote_tmux_session']}",
                f"Remote workspace: {bootstrap.remote_workspace_root}",
            ],
        )


class AdapterRegistry:
    def __init__(self, spec: ProjectSpec) -> None:
        self.spec = spec
        self.router = ExecutionRouter(spec)
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
        execution_plan = self.router.choose_host(tool, state)
        return adapter.run(tool, self.spec, project_root, state, state_path, result_json_path, execution_plan)
