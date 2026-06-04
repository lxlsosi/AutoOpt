# Security Policy

## Supported versions

The `main` branch is the only supported development line until the project has tagged releases.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting or open a minimal issue that does not include exploit details, credentials, private hostnames, private dataset paths, or personal information. A maintainer will follow up with a private channel if more detail is needed.

## Data and credential policy

AutoOpt examples must not require private datasets, real cloud buckets, real access keys, production hostnames, or personal paths. Use placeholder values in committed files and provide local credentials through ignored files or environment variables.

High-risk workflow changes should require human review, especially changes that affect:

- frozen evaluation sets
- labels or test data
- metric thresholds
- compute budgets
- artifact deletion
- release-critical behavior
