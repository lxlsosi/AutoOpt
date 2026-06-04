# Codex for OSS Preparation

This document explains why AutoOpt is a good fit for Codex-assisted open-source maintenance and how the project intends to use Codex safely.

## Project summary

AutoOpt is an orchestration framework for evaluation-constrained AI coding agents in ML and algorithm engineering workflows.

It externalizes the durable parts of an agent workflow:

- stable project contracts
- persistent job state
- tool registries
- compute adapters
- artifacts and metrics
- frozen evaluation sets
- human approval gates

The goal is to let maintainers use Codex-style agents to help diagnose, implement, evaluate, and document changes while preserving reproducibility and reviewability.

## Why Codex is useful for AutoOpt

AutoOpt has several maintainer tasks that are well suited to Codex:

1. Implementing adapters for execution backends such as Slurm, Ray, Kubernetes, GitHub Actions, and local shell runners.
2. Adding JSON Schema validation for `contract.json` and `project.json`.
3. Writing golden tests for state-machine transitions and failure recovery.
4. Reviewing pull requests that affect evaluation, budget accounting, or human-gate logic.
5. Refactoring orchestration code while preserving file formats and user-facing contracts.
6. Producing examples and documentation for new ML workflows.
7. Generating migration guides as project contracts evolve.

## Application fit

AutoOpt is a good fit for the Codex for Open Source program when the application emphasizes maintainer workflow rather than popularity metrics.

Current strengths:

- public MIT-licensed repository
- clear Codex-assisted maintainer roadmap
- deterministic smoke test and CI workflow
- explicit data, credential, and human-gate policies
- OpenAI Responses worker boundary that can use API credits for core OSS maintenance work

Current limitations:

- early project with low public adoption
- no package download history yet
- limited community activity until more issues, examples, and releases exist

The application should be accurate about those limitations and explain why the project is still OSS-relevant: AutoOpt addresses the common maintainer problem of making AI coding-agent work reproducible, inspectable, and bounded by evaluation contracts.

## Safety model

AutoOpt should treat a coding agent as a bounded maintainer assistant, not as the owner of the project objective.

A stable contract should define:

- objective
- success metrics
- frozen evaluation suites
- data policy
- compute budget
- allowed tools
- approval-required actions

The agent may propose and execute bounded steps, but the following actions should require human approval:

- changing benchmark labels or test sets
- using unverified external datasets
- spending large compute budgets
- deleting artifacts or checkpoints
- changing release-critical behavior
- disabling validation or safety checks
- modifying threshold logic that affects downstream decisions

## Maintainer workflow with Codex

A recommended workflow is:

1. Open an issue with target behavior and acceptance criteria.
2. Ask Codex to inspect the relevant modules and propose a small plan.
3. Let Codex implement the change on a branch.
4. Run tests, examples, and static checks.
5. Ask Codex to summarize the diff, risks, and verification evidence.
6. Require a human maintainer to approve changes to contracts, evaluation sets, budget logic, and release behavior.

## Candidate roadmap for Codex-assisted work

- Implement an OpenAI Responses worker behind a stable worker interface.
- Add JSON Schema validation for project and contract files.
- Add CI coverage for package import, CLI smoke tests, and schema validation.
- Add Slurm and Ray adapter examples.
- Add a GitHub Actions example that runs a small AutoOpt workflow on pull requests.
- Add deterministic examples that do not require private data or internal infrastructure.
- Add PR-review checklists for high-risk changes.

## API credit use

API credits should be used only for project maintenance workflows, such as:

- running the OpenAI Responses worker against public AutoOpt issues and PRs
- generating structured decisions for bounded tool calls
- reviewing changes to state transitions, schema rules, and safety gates
- drafting migration notes for contract and project file changes
- maintaining examples and documentation

Do not submit confidential information in the application, and do not store personal email addresses, OpenAI organization IDs, API keys, or private infrastructure details in this repository.

## Why this is OSS-relevant

AutoOpt targets a common open-source maintenance problem: how to let AI coding agents help with long-running engineering work without hiding state in a conversation, mutating benchmarks, or making unreviewed changes to evaluation logic.

The project is intentionally structured around durable files, explicit contracts, reproducible artifacts, and human gates so external contributors can inspect and improve the workflow.
