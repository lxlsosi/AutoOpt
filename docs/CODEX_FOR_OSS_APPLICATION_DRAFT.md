# Codex for OSS Application Draft

This file is a non-confidential draft for the Codex for Open Source application. Do not commit personal names, email addresses, OpenAI organization IDs, API keys, or private infrastructure details.

## Field-by-field notes

| Field | Suggested value |
| --- | --- |
| Last name | Fill manually. Do not store it in this repository. |
| First name | Fill manually. Do not store it in this repository. |
| Email | Use the email associated with your ChatGPT account. Do not store it in this repository. |
| GitHub username | Use the public GitHub account that owns or maintains the repository. Make sure the profile is public. |
| GitHub repository URL | `https://github.com/lxlsosi/AutoOpt` |
| Maintainer role | Choose `Primary maintainer` if you own the repository and control releases; otherwise choose `Core maintainer`. |
| Interested in | Select `Project API credits`. Select `Codex Security` only if you want security review for this repository and have authority to administer it. |
| OpenAI organization ID | Fill manually from the OpenAI API dashboard. Do not store it in this repository. |

## Eligibility answer draft

AutoOpt is an early public MIT-licensed Python project for evaluation-constrained AI coding-agent workflows. It helps OSS maintainers make Codex-assisted ML and algorithm work reproducible through explicit contracts, persistent state, artifact logs, frozen evaluation sets, and human approval gates. Adoption is currently small, so the strongest eligibility argument is ecosystem importance rather than popularity.

## API credit use draft

I would use API credits for core AutoOpt maintenance: running the OpenAI Responses worker on public issues and PRs, reviewing changes to state transitions and safety gates, generating schema and migration tests, drafting release notes, and maintaining examples that demonstrate bounded Codex-assisted workflows without private data or credentials.

## Additional notes draft

AutoOpt now includes CI smoke tests, contribution/security/privacy docs, a sanitized local demo, and placeholder-only infrastructure examples. I will not submit confidential information, personal data, private datasets, credentials, or unauthorized repositories for Codex Security or API-credit workflows.

## Before submitting

- Recheck current GitHub stars, forks, issues, and releases.
- Make the repository description non-empty on GitHub.
- Add topics such as `ai-agents`, `codex`, `mlops`, `orchestration`, and `evaluation`.
- Confirm the repository is public and the applicant has maintainer/admin authority.
- Keep each free-text answer under the form's 500-character limit.
