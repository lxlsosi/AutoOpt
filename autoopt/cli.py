from __future__ import annotations

import argparse
import json
from pathlib import Path

from autoopt.orchestrator import Orchestrator
from autoopt.project_loader import load_project
from autoopt.state_store import FileStateStore
from autoopt.workers import OpenAIResponsesWorker, RuleBasedWorker


def _build_worker(name: str, model: str) -> RuleBasedWorker | OpenAIResponsesWorker:
    if name == "openai":
        return OpenAIResponsesWorker(model=model, fallback=RuleBasedWorker())
    return RuleBasedWorker()


def run_command(args: argparse.Namespace) -> int:
    spec, contract, walkthrough = load_project(args.project)
    state_dir = Path(spec.project_root) / spec.runtime.get("state_dir", ".autoopt/jobs")
    store = FileStateStore(str(state_dir))
    worker = _build_worker(args.worker or spec.runtime.get("default_worker", "rule-based"), args.model)
    orchestrator = Orchestrator(spec, contract, walkthrough, worker, store)
    state = orchestrator.run(job_id=args.job_id, max_turns=args.max_turns)
    print(
        json.dumps(
            {
                "job_id": state.job_id,
                "phase": state.phase,
                "attempts": state.attempts,
                "best_metric": state.best_metric,
                "budget_spent": state.budget_spent,
                "approval_required": state.approval_required,
                "blocked_reason": state.blocked_reason,
                "state_path": str(store.state_path(state.job_id)),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


def inspect_command(args: argparse.Namespace) -> int:
    spec, _, _ = load_project(args.project)
    state_dir = Path(spec.project_root) / spec.runtime.get("state_dir", ".autoopt/jobs")
    store = FileStateStore(str(state_dir))
    state = store.load(args.job_id)
    if state is None:
        raise SystemExit(f"No state found for job '{args.job_id}'")
    print(json.dumps(state.to_dict(), indent=2, ensure_ascii=False))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="AutoOpt autonomous algorithm engineer")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    run_parser = subparsers.add_parser("run", help="Run or resume a job")
    run_parser.add_argument("--project", required=True, help="Path to project.json")
    run_parser.add_argument("--job-id", required=True, help="Stable job identifier")
    run_parser.add_argument("--max-turns", type=int, default=8, help="Maximum turns for this invocation")
    run_parser.add_argument("--worker", choices=["rule-based", "openai"], default=None)
    run_parser.add_argument("--model", default="gpt-5.4")
    run_parser.set_defaults(func=run_command)

    inspect_parser = subparsers.add_parser("inspect", help="Inspect persisted job state")
    inspect_parser.add_argument("--project", required=True, help="Path to project.json")
    inspect_parser.add_argument("--job-id", required=True, help="Stable job identifier")
    inspect_parser.set_defaults(func=inspect_command)

    args = parser.parse_args()
    raise SystemExit(args.func(args))
