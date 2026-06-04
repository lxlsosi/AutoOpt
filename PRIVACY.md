# Privacy and Data Policy

AutoOpt stores workflow state, artifact references, and metrics so agent work can be resumed and reviewed. The repository should only contain public code, synthetic examples, placeholder infrastructure, and documentation.

Do not commit:

- API keys, cloud credentials, tokens, or passwords
- real user data, private audio, private documents, or private datasets
- personal email addresses, phone numbers, home directories, or account names
- internal hostnames, private IPs, production bucket names, or non-public paths
- generated `.autoopt/`, `artifacts/`, logs, checkpoints, or model weights

Use environment variables, ignored `*.local` files, or local secret managers for private configuration. When sharing logs, redact command output that includes private paths, credentials, account IDs, dataset records, or user identifiers.
