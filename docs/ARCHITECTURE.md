# AutoOpt Architecture

## 1. Design principles

AutoOpt is designed for safe, reproducible AI-agent-assisted algorithm engineering.

- A task is a state machine, not a single long conversation.
- Durable memory lives in external state and artifacts, not only in model context.
- Long-running data, training, and evaluation work is delegated to external jobs.
- Every turn should leave checkpoints, summaries, failure paths, and artifact references.
- Project contracts are frozen before optimization; agents should not silently rewrite goals.
- High-risk actions should stop at explicit human gates.

## 2. Project files

Each AutoOpt project should contain at least three files:

1. `walkthrough.md`
2. `contract.json`
3. `project.json`

For distributed or remote execution, `execution_topology` should also be part of the stable project configuration.

### `contract.json`

The contract defines stable constraints:

- `objective`
- `success_metrics`
- `frozen_eval_sets`
- `constraints`
- `data_policy`
- `compute_policy`
- `human_gates`

### `project.json`

The project configuration defines the execution layer:

- `tool_registry`
- `decision_rules`
- `runtime`
- `execution_topology`

Example tool registry entry:

```json
{
  "discover_data": {
    "adapter": "data",
    "description": "Catalog candidate datasets",
    "command": "python3 scripts/data_pipeline.py discover --project-root {project_root} --result-json {result_json}",
    "produces_artifacts": ["artifacts/data/source_catalog.json"],
    "budget_cost": 5
  }
}
```

Example decision rule:

```json
{
  "name": "discover sources",
  "when": {
    "missing_artifacts": ["artifacts/data/source_catalog.json"]
  },
  "phase": "diagnose",
  "tools": ["discover_data"],
  "summary": "Catalog candidate sources before any training.",
  "followup_phase": "propose"
}
```

## 3. Persistent state

AutoOpt persists job state so that agent work can resume across turns and failures. Typical fields include:

- `job_id`
- `thread_id`
- `phase`
- `attempts`
- `attempts_by_tool`
- `goal`
- `completed_steps`
- `failed_approaches`
- `artifacts`
- `last_summary`
- `deadline_at`
- `dataset_version`
- `eval_suite_version`
- `latest_metrics`
- `best_metric`
- `metrics_history`
- `budget_spent`
- `approval_required`
- `hypotheses_tried`
- `blocked_reason`
- `last_execution_target`
- `pending_jobs`
- `execution_history`
- `phase_history`
- `checkpoints`

## 4. Execution topology

AutoOpt separates control from execution.

- **Controller**: runs the orchestrator, worker, state store, and summaries.
- **Execution workers**: run data processing, training, evaluation, or submitted jobs.

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

The orchestrator should not need to live on a GPU worker. It records the target host and routing reason in state, while wrappers or adapters submit the actual work.

For long-running training:

1. The current turn submits a background job.
2. The returned job handle is recorded in `pending_jobs`.
3. A later turn polls job status.
4. When the job completes, AutoOpt collects logs, checkpoints, and metrics.
5. The workflow proceeds to evaluation and reflection.

## 5. Adapter surfaces

### Data adapters

- enumerate candidate sources
- download and validate datasets
- generate manifests
- record license, checksum, coverage, and leakage risk

### Compute adapters

- submit training or evaluation jobs
- return job identifiers
- poll job status
- collect metrics, logs, checkpoints, and model paths

### Evaluation adapters

- run frozen benchmarks
- generate confusion matrices
- report per-class metrics
- produce failure summaries
- detect regressions

## 6. Why start with a rule-based worker

The rule-based worker exists to validate the stable parts before introducing model-driven behavior:

- state-machine boundaries
- checkpoint granularity
- artifact protocol
- tool-call protocol
- approval gates
- failure recovery

After these boundaries are stable, a Codex-style or OpenAI Responses worker can be attached through the same tool and state interfaces.

## 7. Production hardening

A production deployment should replace examples with project-specific adapters:

- replace `ShellAdapter` with a platform adapter
- replace mock scripts with real submit/poll/collect commands
- define a stable worker prompt and output schema
- replace `.autoopt/jobs` with a durable store when necessary
- validate contracts and projects with JSON Schema
- audit changes to evaluation and release logic

If an existing project already exists, use AutoOpt as a control plane:

- keep the AutoOpt project layer separate
- link the real training or algorithm project as `source_project`
- let agents modify wrappers, adapters, and decision rules first
- modify core training code only after the change scope is explicit

## 8. Human gate recommendations

Require approval for:

- uncertain external dataset licenses
- large compute budget usage
- abnormal metric shifts
- suspected data leakage
- repeated failures of the same approach
- changes to test sets, labels, thresholds, or release-critical behavior
- deletion of artifacts, logs, or checkpoints
- disabling validation or safety checks

## 9. Codex integration boundary

A Codex-style worker should receive only the information needed for the next bounded step:

- current state summary
- relevant contract fields
- relevant walkthrough sections
- tool registry subset
- artifact references
- prior failure summaries

It should return structured decisions:

- proposed action
- tools to invoke
- expected artifacts
- risk level
- whether human approval is required
- concise summary for the next turn

The repository should treat Codex as a maintainer assistant that proposes and executes bounded changes under the project contract, not as an unrestricted autonomous maintainer.