# AutoOpt

AutoOpt is an open-source orchestration framework for evaluation-constrained AI coding agents in machine learning and algorithm engineering workflows.

It is designed for maintainers who want AI agents to help diagnose, implement, evaluate, and document iterative algorithm improvements without losing reproducibility, changing the project goal implicitly, or bypassing human review.

## Why AutoOpt exists

Long-running ML and algorithm work does not fit well into a single chat thread. Useful progress depends on durable state, frozen evaluation sets, logs, metrics, checkpoints, compute budgets, and repeatable handoffs between humans and tools.

AutoOpt treats an agent workflow as a state machine rather than a long conversation:

- The project objective lives in a stable contract, not only in model context.
- Each agent turn performs a bounded step and leaves a checkpoint.
- Training, data processing, and evaluation run as external jobs.
- The agent proposes, executes, polls, evaluates, and reflects through explicit tools.
- Risky actions stop at a human gate.

## Core concepts

| Concept | Purpose |
| --- | --- |
| `contract.json` | Stable project goal, metrics, constraints, data policy, compute policy, and human gates. |
| `project.json` | Tool registry, runtime configuration, decision rules, and execution topology. |
| `walkthrough.md` | Human-readable project context and operating notes. |
| `JobState` | Persistent state for each optimization job. |
| `artifacts/` | Data manifests, analysis reports, metrics, logs, checkpoints, and summaries. |
| `execution_topology` | Separation between controller hosts and compute workers. |

## State flow

```text
queued -> diagnose -> propose -> execute -> evaluate -> reflect -> handoff/done/failed
```

## Quickstart

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
python -m unittest discover -s tests

autoopt run --project Arab/project.json --job-id arab-demo --max-turns 12
autoopt inspect --project Arab/project.json --job-id arab-demo
autoopt project init-linked \
  --name "My Project" \
  --target-dir ./MyProject \
  --external-project /path/to/external/repo
```

The bundled `Arab/` directory is a small demonstration project. It is intended to exercise the orchestration layer and generate local artifacts such as:

- `artifacts/data/*.json`
- `artifacts/analysis/*.json`
- `artifacts/metrics/*.json`
- `.autoopt/jobs/*.json`

The bundled examples use synthetic or placeholder infrastructure. Do not commit real credentials, private datasets, private hostnames, production buckets, or personal paths.

## Agent worker model

The default worker is rule-based so that the workflow contract, state transitions, artifact protocol, and tool registry can be validated before introducing model-driven behavior.

The same framework can be connected to a Codex-style or OpenAI Responses worker through a stable interface:

```bash
OPENAI_API_KEY=... autoopt run \
  --project Arab/project.json \
  --job-id arab-openai \
  --worker openai \
  --model <model-name>
```

The intended model-worker contract is:

- input: externalized state, project contract, walkthrough, and tool registry
- output: structured decisions and bounded tool calls
- storage: explicit project artifacts, not hidden conversation memory
- safety: approval gates for evaluation, data, compute, and release-critical changes

## Execution topology

AutoOpt separates control and execution:

- **Controller**: runs the orchestrator, worker, state store, and summaries.
- **Execution workers**: run data processing, training, evaluation, or long-running jobs.

Example topology:

```json
{
  "execution_topology": {
    "controller_host": "controller-01",
    "default_local_host": "controller-01",
    "default_compute_hosts": ["gpu-worker-01", "gpu-worker-02"],
    "routing_profiles": {
      "data_ops": ["controller-01"],
      "evaluation": ["controller-01"],
      "gpu_train": ["gpu-worker-01", "gpu-worker-02"]
    }
  }
}
```

For long-running jobs, AutoOpt should submit a background job, store a job handle in state, poll in a later turn, and collect logs, checkpoints, and metrics before moving to evaluation.

## Adapting a real project

A recommended pattern is to keep AutoOpt as the control plane and link an existing training or algorithm project into a new AutoOpt project directory:

```bash
autoopt project init-linked \
  --name "New Algo Project" \
  --target-dir ./NewAlgoProject \
  --external-project /absolute/path/to/real/project
```

This creates:

- `project.json`
- `contract.json`
- `walkthrough.md`
- a minimal diagnostic script
- a `source_project` link to the real project

Then maintainers can let an AI worker adapt wrappers, adapters, decision rules, and reporting logic without immediately modifying the core training project.

## Safety principles

AutoOpt is designed around conservative agent automation:

1. Freeze the objective and evaluation suite before optimization.
2. Record every turn, tool call, artifact, metric, and failure path.
3. Require explicit approval before changing labels, test sets, budgets, or release-critical behavior.
4. Treat the agent as a bounded proposer/executor, not the owner of the project goal.
5. Keep reproducible artifacts outside the model thread.

## Open-source readiness

AutoOpt is structured for Codex-assisted maintenance work:

- deterministic rule-based worker for local smoke tests
- explicit OpenAI Responses worker boundary for model-driven decisions
- committed examples that avoid private data and use placeholder infrastructure
- CI smoke test for package import and end-to-end example execution
- documented contribution, security, and privacy policies

Good first maintainer tasks for Codex are schema validation, transition tests, execution adapters, PR-review checklists, and documentation examples.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Codex for OSS preparation](docs/CODEX_FOR_OSS.md)
- [Codex for OSS application draft](docs/CODEX_FOR_OSS_APPLICATION_DRAFT.md)
- [Contributing](CONTRIBUTING.md)
- [Security policy](SECURITY.md)
- [Privacy and data policy](PRIVACY.md)

## Roadmap

- Add an OpenAI Responses worker implementation behind a stable worker interface.
- Add JSON Schema validation for `contract.json` and `project.json`.
- Add golden tests for state-machine transitions.
- Add Slurm, Ray, Kubernetes, and GitHub Actions adapter examples.
- Add deterministic OSS examples that do not depend on private data or internal infrastructure.
- Add PR-review helpers for risky changes to evaluation and budget logic.

## License

MIT License. See [LICENSE](LICENSE).
