# Security Policy

## Reporting a vulnerability

Report privately via GitHub Security Advisories:
<https://github.com/AdarGit008/mcgyvr/security/advisories/new>

Please do not open a public issue for a vulnerability.

## Threat model

mcgyvr executes model-authored code and contract-declared commands
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
   the host in tempdir mode. Delivery judges the accepted file again in your
   own checkout, on the host, and there it does not run eslint or prettier
   over a file that tool would load as its own configuration
   (`eslint.config.mjs`, `prettier.config.js` and the like); the run says so.
   A module such a config imports by path is still loaded when the tool runs.
   A source that is not a git repository is copied
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

## Who can read a prompt

A request a rider sends through a hub reaches a model server someone runs.
Where its text is in clear:

- **A ride (a relief rung) whose host's agent advertises a seal key** is sealed
  end to end (`mcgyvr.seal`): the hub carries the envelope and the answer's
  events without the keys to open them. In clear on the hub: the model asked
  for, whether it streams, the sizes and timing of the request and of each
  answer event, the answer's model name and its token counts (`usage`,
  `timings`, which the hub charges by), and who rode whose unit. **The host
  reads the prompt and the answer**: their agent opens the request and their
  model server answers it.
- **A ride to a rung with no key** (an older agent or hub), **a request to the
  general or a crew pool** (served by a pooled session's head), and **any
  request a third-party client sends** in clear: the hub, the head's rig and
  the unit's host can read it.

What sealing does not yet do: the hub is the key directory and the key is not
signed (the `seal.sig` slot is for rig identity), so a hub that hands a rider a
key of its own can read what is sealed to it; sealing keeps out a hub that
relays honestly and reads what passes, not one that lies about whose key it
lists. A hub can still drop or cut an answer (the rider sees it fail, not a
changed answer), and it may send one sealed request again.
