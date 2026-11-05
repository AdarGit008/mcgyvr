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

## Who else is in a run that rides a hub

A rung is not always yours. A relief rung (`mcgyvr rig rungs sync`) is lent by
another member's machine, and a unit of scope `crew` or `anyone` is served from
your crews' or anyone's machines. Four parties then have a part in a run:

- **The hub** relays each request and answer, in plaintext: TLS ends there.
  It picks the machine that serves a request, within the scope the request
  names, and it writes the relief rungs and crew units a sync fetches. It never
  reaches your machine: your machine dials it. A unit of scope `own` that a
  hub serves is trusted as yours on the hub's word alone.
- **You, riding** another member's unit, send what a prompt carries: the
  system bundle, the task, the full text of the files the contract names
  (secret-looking file names are skipped) and earlier failure notes, redacted
  on a best-effort basis. The hub and the host can read all of it.
- **The host** that serves a ride reads every prompt sent to its unit and
  answers with any text it likes. That text is the code your gate runs and
  your delivery commits. A reply naming a model other than the one the hub
  matched passes the rung over.
- **A peer on your local network** can reach what a task container on Docker's
  default network can reach, and anything your machine serves on its network.

What the gate and delivery do with code from a rung that is not yours:

1. **It never runs with a network.** In `sandbox.mode: docker` it runs in a
   second task container started with `--network none`, whatever
   `sandbox.network` says (`none` included), with no capabilities
   (`--cap-drop ALL`), no gaining privileges (`no-new-privileges`), a read-only
   root and a `/tmp` and `/var/tmp` in memory, started again before every lent
   try after its first, so what one host's code leaves outside the workspace
   (which every try resets) or running is gone before the next host's runs.
   Your own rungs' code keeps the task's own container, which never runs a
   stranger's code. In the `tempdir` sandbox (by name, or as
   the fallback) it would run on this host, so a try on such a rung is declined
   before anything is sent, unless the repository is listed under
   `sandbox.lent_code_on_host`.
2. **It never lands unmarked.** Its commit carries `Mcgyvr-Source:` (`crew` or
   `anyone`) and `Mcgyvr-Model:` trailers, never the machine or member that
   served it. Under `delivery.lent_code: branch` (the default) it is committed
   onto a branch of its own from the base it was judged against —
   `mcgyvr/<contract id>`, or `-2`, `-3`, … beside an earlier run's —
   whatever `delivery.commit` says, and never written into your checkout;
   `checkout` delivers it as your own rungs' code.

What stays yours to weigh: the container is Docker's boundary, not a virtual
machine; the second look delivery takes at an accepted file runs on this host,
with the checkers the threat model's first property names; the draws of one
try share the second container's `/tmp`, and a rider running as root shares
its dependency folders (`.venv`, `node_modules`) from one lent try to the
next; and a lent change is a stranger's code until you have read it.
