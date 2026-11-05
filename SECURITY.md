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

## Model servers mcgyvr renders

A llama.cpp or vLLM server that `mcgyvr emit` writes into a container listens
on 127.0.0.1 when its unit is `expose: local` (`src/mcgyvr/emit.py`,
`listens_on`), and on every interface when it is `expose: lan`; a unit that
states neither is `local` when its address names this machine and `lan` when
it names another host (`mcgyvr.serving.exposure`). A `lan` unit listens on
every interface and asks every request for an API key mcgyvr makes for it
(`src/mcgyvr/unitkey.py`): 256 bits, kept at mode 0600 in
`unit-keys/<host>-<port>.env` in the data folder of the machine that runs
`mcgyvr emit` (not the rig's, which `docker compose` reaches over ssh), written
and read by
`atomic.write_private` and `read_private` (no link, owner and mode checked), and
handed to the server through the compose service's
`env_file`, which `docker compose` reads where it runs, so the key is never in
a compose file or in `fleet.yaml`. What runs on the rig for a read, a lock's
sample or `fleet probe` (rig-units.sh, the lock's harness) is handed the key on
ssh's stdin with its own text, never on a command line or in a file there; a
rig agent shares a keyed unit only when its own data folder holds the key. llama-server b11960 then asks for it on
every path but `/health` and `/v1/health`; vLLM asks for it under `/v1`,
`/v2` and `/inference` only, so its `/metrics` and the sleep routes stay open
to whoever reaches the port. The key travels as a bearer token over plain HTTP:
anyone who can read the LAN's traffic can read it. A `--host` or
`LLAMA_ARG_HOST` a unit's own launch states is rendered as stated, with no key
unless the unit also states `lan`. A native unit listens on 127.0.0.1 alone,
and a pooled rpc worker on its tunnel address, with no key (rpc-server has no
authentication).
