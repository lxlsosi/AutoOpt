from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class Phase(str, Enum):
    QUEUED = "queued"
    DIAGNOSE = "diagnose"
    PROPOSE = "propose"
    EXECUTE = "execute"
    EVALUATE = "evaluate"
    REFLECT = "reflect"
    HANDOFF = "handoff"
    DONE = "done"
    FAILED = "failed"


TERMINAL_PHASES = {Phase.HANDOFF.value, Phase.DONE.value, Phase.FAILED.value}


@dataclass
class ProjectContract:
    project_id: str
    objective: str
    goal: str
    success_metrics: list[dict[str, Any]]
    frozen_eval_sets: list[str]
    constraints: list[str]
    data_policy: dict[str, Any]
    compute_policy: dict[str, Any]
    human_gates: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProjectContract":
        known = {
            "project_id",
            "objective",
            "goal",
            "success_metrics",
            "frozen_eval_sets",
            "constraints",
            "data_policy",
            "compute_policy",
            "human_gates",
        }
        metadata = {key: value for key, value in data.items() if key not in known}
        return cls(
            project_id=data["project_id"],
            objective=data["objective"],
            goal=data.get("goal", data["objective"]),
            success_metrics=data.get("success_metrics", []),
            frozen_eval_sets=data.get("frozen_eval_sets", []),
            constraints=data.get("constraints", []),
            data_policy=data.get("data_policy", {}),
            compute_policy=data.get("compute_policy", {}),
            human_gates=data.get("human_gates", []),
            metadata=metadata,
        )


@dataclass
class ToolSpec:
    name: str
    adapter: str
    description: str
    command: str
    produces_artifacts: list[str] = field(default_factory=list)
    budget_cost: float = 0.0
    requires_approval: bool = False
    metric_scope: str = "auxiliary"
    workload_profile: str = "default"
    candidate_hosts: list[str] = field(default_factory=list)
    dispatch_strategy: str = "least_used"
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> "ToolSpec":
        known = {
            "adapter",
            "description",
            "command",
            "produces_artifacts",
            "budget_cost",
            "requires_approval",
            "metric_scope",
            "workload_profile",
            "candidate_hosts",
            "dispatch_strategy",
        }
        metadata = {key: value for key, value in data.items() if key not in known}
        return cls(
            name=name,
            adapter=data["adapter"],
            description=data["description"],
            command=data["command"],
            produces_artifacts=data.get("produces_artifacts", []),
            budget_cost=float(data.get("budget_cost", 0.0)),
            requires_approval=bool(data.get("requires_approval", False)),
            metric_scope=data.get(
                "metric_scope",
                "evaluation" if data["adapter"] == "evaluation" else "auxiliary",
            ),
            workload_profile=data.get("workload_profile", "default"),
            candidate_hosts=data.get("candidate_hosts", []),
            dispatch_strategy=data.get("dispatch_strategy", "least_used"),
            metadata=metadata,
        )


@dataclass
class ExecutionHost:
    name: str
    mode: str = "local"
    ssh_target: str | None = None
    project_root: str | None = None
    roles: list[str] = field(default_factory=list)
    local_aliases: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> "ExecutionHost":
        known = {"mode", "ssh_target", "project_root", "roles", "local_aliases"}
        metadata = {key: value for key, value in data.items() if key not in known}
        return cls(
            name=name,
            mode=data.get("mode", "local"),
            ssh_target=data.get("ssh_target"),
            project_root=data.get("project_root"),
            roles=data.get("roles", []),
            local_aliases=data.get("local_aliases", []),
            metadata=metadata,
        )


@dataclass
class ExecutionTopology:
    controller_host: str | None = None
    default_local_host: str | None = None
    default_compute_hosts: list[str] = field(default_factory=list)
    routing_profiles: dict[str, list[str]] = field(default_factory=dict)
    hosts: dict[str, ExecutionHost] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExecutionTopology":
        known = {
            "controller_host",
            "default_local_host",
            "default_compute_hosts",
            "routing_profiles",
            "hosts",
        }
        metadata = {key: value for key, value in data.items() if key not in known}
        hosts = {
            name: ExecutionHost.from_dict(name, host_data)
            for name, host_data in data.get("hosts", {}).items()
        }
        return cls(
            controller_host=data.get("controller_host"),
            default_local_host=data.get("default_local_host", data.get("controller_host")),
            default_compute_hosts=data.get("default_compute_hosts", []),
            routing_profiles=data.get("routing_profiles", {}),
            hosts=hosts,
            metadata=metadata,
        )


@dataclass
class DecisionRule:
    name: str
    when: dict[str, Any]
    phase: str
    tools: list[str] = field(default_factory=list)
    summary: str = ""
    followup_phase: str | None = None
    set_fields: dict[str, Any] = field(default_factory=dict)
    requires_human: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DecisionRule":
        return cls(
            name=data["name"],
            when=data.get("when", {}),
            phase=data["phase"],
            tools=data.get("tools", []),
            summary=data.get("summary", ""),
            followup_phase=data.get("followup_phase"),
            set_fields=data.get("set_fields", {}),
            requires_human=bool(data.get("requires_human", False)),
        )


@dataclass
class ProjectSpec:
    project_id: str
    name: str
    project_root: str
    walkthrough_path: str
    contract_path: str
    runtime: dict[str, Any]
    execution_topology: ExecutionTopology
    tool_registry: dict[str, ToolSpec]
    decision_rules: list[DecisionRule]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TurnDecision:
    phase: str
    summary: str
    tools: list[str] = field(default_factory=list)
    followup_phase: str | None = None
    requires_human: bool = False
    set_fields: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolExecutionOutcome:
    tool_name: str
    success: bool
    summary: str
    artifacts: dict[str, str] = field(default_factory=dict)
    metrics: dict[str, float] = field(default_factory=dict)
    dataset_version: str | None = None
    eval_suite_version: str | None = None
    gpu_job_id: str | None = None
    hypotheses: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    budget_cost: float = 0.0
    execution_host: str | None = None
    execution_mode: str | None = None
    deferred: bool = False
    count_attempt: bool = True
    pending_job: dict[str, Any] | None = None
    clear_pending_job: bool = False
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""


@dataclass
class JobState:
    job_id: str
    project_id: str
    thread_id: str
    phase: str = Phase.QUEUED.value
    attempts: int = 0
    attempts_by_tool: dict[str, int] = field(default_factory=dict)
    goal: str = ""
    completed_steps: list[dict[str, Any]] = field(default_factory=list)
    failed_approaches: list[dict[str, Any]] = field(default_factory=list)
    hypotheses_tried: list[str] = field(default_factory=list)
    artifacts: dict[str, str] = field(default_factory=dict)
    last_summary: str = ""
    deadline_at: str | None = None
    dataset_version: str | None = None
    eval_suite_version: str | None = None
    latest_metrics: dict[str, float] = field(default_factory=dict)
    best_metric: dict[str, float] = field(default_factory=dict)
    metrics_history: list[dict[str, Any]] = field(default_factory=list)
    gpu_job_id: str | None = None
    budget_spent: float = 0.0
    approval_required: bool = False
    blocked_reason: str | None = None
    last_execution_target: str | None = None
    pending_jobs: dict[str, dict[str, Any]] = field(default_factory=dict)
    execution_history: list[dict[str, Any]] = field(default_factory=list)
    phase_history: list[dict[str, Any]] = field(default_factory=list)
    checkpoints: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    @classmethod
    def create(cls, job_id: str, project_id: str, goal: str, deadline_at: str | None = None) -> "JobState":
        return cls(
            job_id=job_id,
            project_id=project_id,
            thread_id=f"local-{job_id}",
            goal=goal,
            deadline_at=deadline_at,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "JobState":
        return cls(**data)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def touch(self) -> None:
        self.updated_at = utc_now()

    def record_phase(self, phase: str, summary: str) -> None:
        self.phase_history.append(
            {
                "phase": phase,
                "summary": summary,
                "timestamp": utc_now(),
            }
        )
        self.touch()

    def record_checkpoint(self, label: str) -> None:
        self.checkpoints.append(
            {
                "label": label,
                "phase": self.phase,
                "summary": self.last_summary,
                "timestamp": utc_now(),
            }
        )
        self.touch()
