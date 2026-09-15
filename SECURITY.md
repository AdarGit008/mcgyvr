# Security Policy

## Reporting a vulnerability

Report privately via GitHub Security Advisories:
<https://github.com/AdarGit008/mcgyvr/security/advisories/new>

Please do not open a public issue for a vulnerability.

## Threat model

mcgyvr executes model-authored code and contract-declared shell commands
against a repository. Two properties are load-bearing:

1. **Task execution is sandboxed.** By default (`sandbox.mode: docker`) each
   task runs in its own container, torn down afterwards. The temp-directory
   sandbox is weaker: task commands run on the host in a throwaway git
   workspace. It is used when configured (`sandbox.mode: tempdir` or
   `--sandbox tempdir`), or when Docker is configured but no daemon answers;
   either way the run says so.
2. **Provider credentials never enter a task sandbox.** API keys are read
   from the environment by the orchestrator process only; a task container
   receives the repository and the worker endpoint, never a key.

Deviations from either are security-relevant and in scope for a report.
