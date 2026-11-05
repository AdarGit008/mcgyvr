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

## llama.cpp's RPC server

A model split across rigs runs llama.cpp's `rpc-server` on each worker, and
it has no authentication. Two advisories concern the code path it serves:

- **CVE-2026-34159**, critical (CVSS 3.1 9.8): "the RPC backend's
  deserialize_tensor() skips all bounds validation when a tensor's buffer
  field is 0", so anyone with TCP access to the port can read and write the
  process's memory; "This issue has been patched in version b8492."
  (<https://cvefeed.io/vuln/detail/CVE-2026-34159>, published 2026-04-01).
- **CVE-2026-78147**, high (CVSS 3.1 7.3): the same `deserialize_tensor`,
  through `op`/`op_params`, "distinct from CVE-2026-34159 ... which only
  added a buffer==nullptr rejection in create_node() and does not validate op
  or op_params"; listed against build `bec4772f6`, and its upstream issue
  "was closed automatically due to inactivity", so no fixed build is named
  (<https://nvd.nist.gov/vuln/detail/cve-2026-78147>, published 2026-08-23,
  modified 2026-10-12; read from the NVD API on 2026-11-05).

The build mcgyvr pins is `b11960` (`src/mcgyvr/serving/llamacpp.py:64`), above
b8492: the Linux image it names
(`ghcr.io/ggml-org/llama.cpp:server-cuda-b11960`, `llamacpp.py:68`) and the
native archives a Mac or Windows rig fetches are that build. That image holds
`llama-server` alone, so an `rpc-server` in a container always runs an image
the rig's owner chose: a pooled rig's `rig share --image`
(`src/mcgyvr/rig/sharing.py:112`), or a unit's own `image`, which mcgyvr
refuses to guess for a unit that needs RPC (`src/mcgyvr/emit.py:732-762`).
mcgyvr cannot read the build of such an image. **An image that serves
`rpc-server` must be built from llama.cpp b8492 or later.** A rig whose
image is not the pinned one names no RPC protocol in its offer
(`src/mcgyvr/rig/session.py:2440`), so the hub pairs it only with rigs that
name none either.

No build is known to fix CVE-2026-78147, so what bounds it is who can reach
the port:

- A pooled worker's `rpc-server` listens inside its session's tunnel
  container's network namespace, whose nft table drops all input, output and
  forwarding but loopback and the rules added later
  (`src/mcgyvr/rig/pooled.py:112-129`). The only rule that opens the RPC port
  admits TCP from wg0, from the session's peer networks, to the worker's own
  tunnel address and port (`pooled.py:299-310`). WireGuard admits only the
  peers the session's `tunnel_up` named, by their keys, and since this
  release a rig checks each peer's identity signature before it plans the
  tunnel (below).
- The engine containers run as the agent's own unprivileged user with every
  capability dropped, `no-new-privileges`, a seccomp profile, a read-only
  root, a private IPC namespace and pid and memory limits
  (`pooled.py:533-558`, applied to workers at `pooled.py:612-640`); a head's
  API is published on 127.0.0.1 only (`pooled.py:598`).
- Outside pooled sessions, a worker on another machine may bind only a
  private or overlay address, never every interface, loopback or a public
  address (`src/mcgyvr/serving/llamacpp.py:424-433`).

So an attacker must first be a peer of the session (or on the owner's own
private network, for units the owner runs): a rig the hub put in the session
with you. A compromised peer can still reach the RPC port it was given.

## Rig identity keys

The hub is the directory rigs learn each other's per-session WireGuard keys
from. Each rig keeps a long-lived Ed25519 identity key, made at `rig join` (or
the first `rig run` of a rig that joined before) and kept beside the rig token
as `rig-identity.json`, private to its owner as the token is
(`src/mcgyvr/rig/identity.py`). Its public half goes in every `hello`; the hub
binds it to the rig at the first hello that names one, and refuses a later
hello naming another (`machine_mismatch`) until the owner rotates it on the
rig page. The rig signs each session's tunnel key with it, the hub forwards
the key and the signature in `tunnel_up`, and the peer checks the signature
and pins the identity key by rig id in `rig-peers.json`. A peer whose identity
key changed, whose tunnel key its identity did not sign, or for which the hub
sends no key once one is pinned is refused before any tunnel is planned.

What this does not do: **the hub can still stand in for a peer on first
contact**, since the first identity key a rig sees for a peer is the one the
hub hands it. Compare fingerprints out of band to close that: `mcgyvr rig
status` prints this rig's, `mcgyvr rig peers` the ones pinned here, and the
hub shows each rig's on its rig page and in a session's members. After a
peer's owner rotates its key, `mcgyvr rig peers --forget <rig-id>` drops the
old pin once you have compared the new fingerprint with them. A peer from
before identity keys sends none and is taken as before, unpinned; once a
rig's key is bound, the hub refuses a hello from it that names none, so
stripping the key would cut the rig off rather than hand its peers no key.
