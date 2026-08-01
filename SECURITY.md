# Security Policy

## Reporting a vulnerability

Report privately via GitHub Security Advisories:
<https://github.com/AdarGit008/mcgyvr/security/advisories/new>

Please do not open a public issue for a vulnerability.

## Threat model

mcgyvr executes model-authored code and contract-declared shell commands
against a repository. Two properties are load-bearing:

1. **Task execution is sandboxed.** Each task runs in its own container,
   torn down afterwards. The temp-directory fallback is weaker and is used
   only when Docker is unavailable.
2. **Provider credentials never enter a task sandbox.** API keys are read
   from the environment by the orchestrator process only; a task container
   receives the repository and the worker endpoint, never a key.

Deviations from either are security-relevant and in scope for a report.
