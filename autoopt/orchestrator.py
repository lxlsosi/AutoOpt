from __future__ import annotations

from pathlib import Path

from autoopt.executor import AdapterRegistry
from autoopt.models import (
    JobState,
    Phase,
    ProjectContract,
    ProjectSpec,
    TERMINAL_PHASES,
    ToolExecutionOutcome,
)
from autoopt.state_store import FileStateStore
from autoopt.workers import Worker


class Orchestrator:
    def __init__(
        self,
        spec: ProjectSpec,
        contract: ProjectContract,
        walkthrough: str,
        worker: Worker,
        store: FileStateStore,
    ) -> None:
        self.spec = spec
        self.contract = contract
        self.walkthrough = walkthrough
        self.worker = worker
        self.store = store
        self.adapters = AdapterRegistry(spec)

    def load_or_create_state(self, job_id: str) -> JobState:
        existing = self.store.load(job_id)
        if existing is not None:
            return existing
        return JobState.create(
            job_id=job_id,
            project_id=self.spec.project_id,
            goal=self.contract.goal,
            deadline_at=self.spec.runtime.get("deadline_at"),
        )

    def run(self, job_id: str, max_turns: int) -> JobState:
        state = self.load_or_create_state(job_id)
        self.store.save(state)

        for _ in range(max_turns):
            if state.phase in TERMINAL_PHASES:
                break
            state = self.run_turn(state)
            self.store.save(state)
            if state.pending_jobs:
                break

        return state

    def run_turn(self, state: JobState) -> JobState:
        decision = self.worker.decide(self.spec, self.contract, self.walkthrough, state)
        state.attempts += 1
        state.phase = decision.phase
        state.last_summary = decision.summary
        state.record_phase(decision.phase, decision.summary)
        state.record_checkpoint("decision")

        for field_name, value in decision.set_fields.items():
            if hasattr(state, field_name):
                setattr(state, field_name, value)

        if decision.requires_human:
            state.approval_required = True
            state.blocked_reason = decision.summary
            state.phase = Phase.HANDOFF.value
            state.record_checkpoint("handoff")
            return state

        if not decision.tools:
            state.phase = decision.followup_phase or decision.phase
            state.record_checkpoint("no_tools")
            return state

        result_dir = Path(self.spec.project_root) / self.spec.runtime.get("state_dir", ".autoopt/jobs") / "tool_results"
        result_dir.mkdir(parents=True, exist_ok=True)
        state_path = str(self.store.state_path(state.job_id))

        for tool_name in decision.tools:
            tool = self.spec.tool_registry[tool_name]
            if tool.requires_approval:
                state.approval_required = True
                state.blocked_reason = f"Tool '{tool_name}' requires human approval."
                state.phase = Phase.HANDOFF.value
                state.record_checkpoint("approval_required")
                return state

            result_json_path = result_dir / f"{state.job_id}-{state.attempts}-{tool_name}.json"

            outcome = self.adapters.run_tool(
                tool=tool,
                project_root=self.spec.project_root,
                state=state,
                state_path=state_path,
                result_json_path=str(result_json_path),
            )
            if outcome.count_attempt:
                state.attempts_by_tool[tool_name] = int(state.attempts_by_tool.get(tool_name, 0)) + 1
            self._merge_outcome(state, outcome, tool)
            state.record_checkpoint(f"tool:{tool_name}")

            if outcome.deferred:
                state.phase = decision.phase
                return state

            if not outcome.success:
                state.phase = Phase.REFLECT.value if decision.phase != Phase.REFLECT.value else Phase.FAILED.value
                return state

        state.phase = decision.followup_phase or decision.phase
        state.record_checkpoint("turn_complete")
        return state

    def _merge_outcome(self, state: JobState, outcome: ToolExecutionOutcome, tool) -> None:
        state.last_summary = outcome.summary
        state.budget_spent += float(outcome.budget_cost)

        if outcome.artifacts:
            state.artifacts.update(outcome.artifacts)

        if outcome.dataset_version:
            state.dataset_version = outcome.dataset_version

        if outcome.eval_suite_version:
            state.eval_suite_version = outcome.eval_suite_version

        if outcome.gpu_job_id:
            state.gpu_job_id = outcome.gpu_job_id

        if outcome.hypotheses:
            for hypothesis in outcome.hypotheses:
                if hypothesis not in state.hypotheses_tried:
                    state.hypotheses_tried.append(hypothesis)

        if outcome.notes:
            state.notes.extend(outcome.notes)

        if outcome.execution_host:
            state.last_execution_target = outcome.execution_host
            state.execution_history.append(
                {
                    "tool": tool.name,
                    "host": outcome.execution_host,
                    "mode": outcome.execution_mode,
                    "timestamp": state.updated_at,
                }
            )

        if outcome.pending_job is not None:
            state.pending_jobs[tool.name] = outcome.pending_job
        if outcome.clear_pending_job:
            state.pending_jobs.pop(tool.name, None)

        if outcome.metrics:
            state.latest_metrics = outcome.metrics
            state.metrics_history.append(
                {
                    "tool": tool.name,
                    "metrics": outcome.metrics,
                    "timestamp": state.updated_at,
                    "metric_scope": tool.metric_scope,
                }
            )
            if tool.metric_scope == "evaluation":
                self._update_best_metrics(state, outcome.metrics)

        step_payload = {
            "tool": tool.name,
            "summary": outcome.summary,
            "success": outcome.success,
            "timestamp": state.updated_at,
            "artifacts": outcome.artifacts,
            "metrics": outcome.metrics,
            "execution_host": outcome.execution_host,
            "execution_mode": outcome.execution_mode,
        }
        if outcome.deferred:
            state.notes.append(outcome.summary)
            return
        if outcome.success:
            state.completed_steps.append(step_payload)
        else:
            step_payload["stderr"] = outcome.stderr
            step_payload["stdout"] = outcome.stdout
            state.failed_approaches.append(step_payload)
            state.blocked_reason = outcome.summary

    def _update_best_metrics(self, state: JobState, metrics: dict[str, float]) -> None:
        metric_modes = {
            metric["name"]: metric.get("mode", "max")
            for metric in self.contract.success_metrics
            if "name" in metric
        }
        for name, value in metrics.items():
            mode = metric_modes.get(name, "max")
            previous = state.best_metric.get(name)
            if previous is None:
                state.best_metric[name] = value
                continue
            if mode == "min" and value < previous:
                state.best_metric[name] = value
            if mode != "min" and value > previous:
                state.best_metric[name] = value
