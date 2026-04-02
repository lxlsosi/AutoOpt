from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from autoopt.models import JobState, Phase, ProjectContract, ProjectSpec, TurnDecision
from autoopt.rule_engine import rule_matches


class Worker:
    def decide(
        self,
        spec: ProjectSpec,
        contract: ProjectContract,
        walkthrough: str,
        state: JobState,
    ) -> TurnDecision:
        raise NotImplementedError


class RuleBasedWorker(Worker):
    def decide(
        self,
        spec: ProjectSpec,
        contract: ProjectContract,
        walkthrough: str,
        state: JobState,
    ) -> TurnDecision:
        for rule in spec.decision_rules:
            if rule_matches(rule, state, spec.project_root):
                return TurnDecision(
                    phase=rule.phase,
                    summary=rule.summary,
                    tools=rule.tools,
                    followup_phase=rule.followup_phase,
                    requires_human=rule.requires_human,
                    set_fields=rule.set_fields,
                )

        return TurnDecision(
            phase=Phase.HANDOFF.value,
            summary="No decision rule matched the current state. Human review is required.",
            tools=[],
            requires_human=True,
        )


class OpenAIResponsesWorker(Worker):
    def __init__(
        self,
        model: str = "gpt-5.4",
        api_key_env: str = "OPENAI_API_KEY",
        fallback: Worker | None = None,
    ) -> None:
        self.model = model
        self.api_key_env = api_key_env
        self.fallback = fallback or RuleBasedWorker()

    def decide(
        self,
        spec: ProjectSpec,
        contract: ProjectContract,
        walkthrough: str,
        state: JobState,
    ) -> TurnDecision:
        api_key = os.environ.get(self.api_key_env)
        if not api_key:
            return self.fallback.decide(spec, contract, walkthrough, state)

        prompt = self._build_prompt(spec, contract, walkthrough, state)
        payload = {
            "model": self.model,
            "store": False,
            "input": [
                {
                    "role": "system",
                    "content": (
                        "You are the decision layer for an autonomous algorithm engineer. "
                        "Return a single JSON object with keys: phase, summary, tools, "
                        "followup_phase, requires_human, set_fields. "
                        "Only choose tools that appear in the provided tool registry."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            "context_management": [
                {
                    "type": "compaction",
                    "compact_threshold": 120000,
                }
            ],
        }

        request = urllib.request.Request(
            "https://api.openai.com/v1/responses",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            return self.fallback.decide(spec, contract, walkthrough, state)

        text = data.get("output_text") or self._extract_output_text(data)
        if not text:
            return self.fallback.decide(spec, contract, walkthrough, state)

        try:
            parsed = self._extract_json(text)
        except json.JSONDecodeError:
            return self.fallback.decide(spec, contract, walkthrough, state)

        return TurnDecision(
            phase=parsed.get("phase", Phase.HANDOFF.value),
            summary=parsed.get("summary", "Model returned an empty decision."),
            tools=parsed.get("tools", []),
            followup_phase=parsed.get("followup_phase"),
            requires_human=bool(parsed.get("requires_human", False)),
            set_fields=parsed.get("set_fields", {}),
        )

    def _build_prompt(
        self,
        spec: ProjectSpec,
        contract: ProjectContract,
        walkthrough: str,
        state: JobState,
    ) -> str:
        tool_registry = {
            name: {
                "adapter": tool.adapter,
                "description": tool.description,
                "produces_artifacts": tool.produces_artifacts,
                "budget_cost": tool.budget_cost,
                "requires_approval": tool.requires_approval,
                "metric_scope": tool.metric_scope,
                "workload_profile": tool.workload_profile,
                "candidate_hosts": tool.candidate_hosts,
                "dispatch_strategy": tool.dispatch_strategy,
            }
            for name, tool in spec.tool_registry.items()
        }
        payload: dict[str, Any] = {
            "project": {
                "project_id": spec.project_id,
                "name": spec.name,
            },
            "execution_topology": {
                "controller_host": spec.execution_topology.controller_host,
                "default_local_host": spec.execution_topology.default_local_host,
                "default_compute_hosts": spec.execution_topology.default_compute_hosts,
                "routing_profiles": spec.execution_topology.routing_profiles,
                "hosts": {
                    name: {
                        "mode": host.mode,
                        "roles": host.roles,
                        "local_aliases": host.local_aliases,
                    }
                    for name, host in spec.execution_topology.hosts.items()
                },
            },
            "contract": {
                "objective": contract.objective,
                "goal": contract.goal,
                "success_metrics": contract.success_metrics,
                "frozen_eval_sets": contract.frozen_eval_sets,
                "constraints": contract.constraints,
                "data_policy": contract.data_policy,
                "compute_policy": contract.compute_policy,
                "human_gates": contract.human_gates,
            },
            "state": state.to_dict(),
            "walkthrough_excerpt": walkthrough[:6000],
            "tool_registry": tool_registry,
            "decision_requirements": {
                "allowed_phases": [phase.value for phase in Phase],
                "never_modify_eval_sets": True,
                "checkpoint_after_every_turn": True,
            },
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    @staticmethod
    def _extract_output_text(data: dict[str, Any]) -> str:
        chunks = []
        for item in data.get("output", []):
            for content in item.get("content", []):
                text = content.get("text")
                if text:
                    chunks.append(text)
        return "\n".join(chunks)

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any]:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise json.JSONDecodeError("No JSON object found", text, 0)
        return json.loads(text[start : end + 1])
