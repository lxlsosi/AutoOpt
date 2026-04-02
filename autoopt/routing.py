from __future__ import annotations

import socket
from dataclasses import dataclass

from autoopt.models import ExecutionHost, JobState, ProjectSpec, ToolSpec


@dataclass
class ExecutionPlan:
    host_name: str
    mode: str
    execution_project_root: str
    ssh_target: str | None = None
    reason: str = ""


class ExecutionRouter:
    def __init__(self, spec: ProjectSpec) -> None:
        self.spec = spec

    def choose_host(self, tool: ToolSpec, state: JobState) -> ExecutionPlan:
        topology = self.spec.execution_topology
        candidates: list[str] = []
        reason = "fallback local"

        if tool.candidate_hosts:
            candidates = list(tool.candidate_hosts)
            reason = f"tool candidate_hosts for {tool.name}"
        elif tool.workload_profile in topology.routing_profiles:
            candidates = list(topology.routing_profiles[tool.workload_profile])
            reason = f"routing profile '{tool.workload_profile}'"
        elif tool.adapter == "compute" and topology.default_compute_hosts:
            candidates = list(topology.default_compute_hosts)
            reason = "default compute hosts"
        elif topology.default_local_host:
            candidates = [topology.default_local_host]
            reason = "default local host"

        if not candidates:
            return ExecutionPlan(
                host_name="local",
                mode="local",
                execution_project_root=self.spec.project_root,
                reason=reason,
            )

        host_name = self._select_host(candidates, tool.dispatch_strategy, state)
        host = topology.hosts.get(host_name) or ExecutionHost(name=host_name, project_root=self.spec.project_root)
        mode = host.mode or "local"
        if self._is_current_host(host):
            mode = "local"

        return ExecutionPlan(
            host_name=host.name,
            mode=mode,
            execution_project_root=host.project_root or self.spec.project_root,
            ssh_target=host.ssh_target,
            reason=reason,
        )

    def _select_host(self, candidates: list[str], strategy: str, state: JobState) -> str:
        if strategy == "first":
            return candidates[0]

        execution_counts = {
            host_name: sum(1 for item in state.execution_history if item.get("host") == host_name)
            for host_name in candidates
        }
        return min(candidates, key=lambda host_name: (execution_counts[host_name], candidates.index(host_name)))

    def _is_current_host(self, host: ExecutionHost) -> bool:
        current_aliases = {
            socket.gethostname().lower(),
            socket.getfqdn().lower(),
            socket.gethostname().split(".")[0].lower(),
        }
        if host.name.lower() in current_aliases:
            return True
        return any(alias.lower() in current_aliases for alias in host.local_aliases)
