# Contributing to AutoOpt

AutoOpt is a small Python project. Keep contributions focused, reproducible, and easy to review.

## Development setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
python -m unittest discover -s tests
```

## Pull request expectations

- Keep changes scoped to one behavior or documentation topic.
- Add or update tests when behavior changes.
- Do not commit generated artifacts from `artifacts/`, `.autoopt/`, caches, datasets, checkpoints, or local credentials.
- Use placeholders for hosts, paths, buckets, accounts, and private infrastructure.
- Preserve human approval gates for evaluation sets, labels, thresholds, compute budgets, and release-critical behavior.

## Issue reports

When reporting a bug, include:

- the command you ran
- the project file path used with `--project`
- the expected behavior
- the observed error or JSON summary
- whether the example uses local execution or remote dispatch

Please remove secrets, private data paths, and personal information before posting logs.
