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
   `--sandbox tempdir`), or when Docker is configured, no daemon answers and
   `sandbox.allow_fallback: true` opts into the fallback; either way the run
   says so. Docker configured with no daemon and no opt-in is refused.
   A task container is on Docker's default network unless
   `sandbox.network: none` takes the network away.
   The gate's checkers that load code from the workspace's own configuration
   (the type checker's plugins, eslint's and prettier's config modules) run
   where the task's commands run: in the task's container in docker mode, on
   the host in tempdir mode. A source that is not a git repository is copied
   into the workspace without the files that hold secrets (dotenv files,
   keys, `.netrc`, cloud and SSH credential folders, registry logins), and
   the run names what it left behind.
2. **Provider credentials never enter a task sandbox.** API keys are read
   from the environment by the orchestrator process only; a task container
   receives the repository and the worker endpoint, never a key. A checker
   the gate runs on the host (ruff, and in tempdir mode the checkers above)
   is handed the same filtered environment, so nothing it runs reaches a key
   either.

Deviations from either are security-relevant and in scope for a report.
