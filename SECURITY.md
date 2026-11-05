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

## Model servers mcgyvr renders

A llama.cpp or vLLM server that `mcgyvr emit` writes into a container listens
on 127.0.0.1 unless its unit states `expose: lan`
(`src/mcgyvr/emit.py`, `listens_on`). A unit that states `lan` listens on
every interface and asks every request for an API key mcgyvr makes for it
(`src/mcgyvr/unitkey.py`): 256 bits, kept at mode 0600 in
`unit-keys/<host>-<port>.env` in the data folder, written and read by
`atomic.write_private` and `read_private` (no link, owner and mode checked), and
handed to the server through the compose service's
`env_file`, which `docker compose` reads where it runs, so the key is never in
a compose file or in `fleet.yaml`. llama-server b11960 then asks for it on
every path but `/health` and `/v1/health`; vLLM asks for it under `/v1`,
`/v2` and `/inference` only, so its `/metrics` and the sleep routes stay open
to whoever reaches the port. The key travels as a bearer token over plain HTTP:
anyone who can read the LAN's traffic can read it. A `--host` or
`LLAMA_ARG_HOST` a unit's own launch states is rendered as stated, with no key
unless the unit also states `lan`. A native unit listens on 127.0.0.1 alone,
and a pooled rpc worker on its tunnel address, with no key (rpc-server has no
authentication).

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
(`src/mcgyvr/rig/session.py:2457`, `:2467`), so the hub pairs it only with rigs that
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
hub hands it. And the hub decides what a first contact is: a peer is known by
the rig id the hub names for it, so a hub can make any peer a first contact by
naming an id this rig has not met, or by sending no key for one it has not
pinned. Only a pinned id is protected; comparing fingerprints is the anchor.
Compare them out of band: `mcgyvr rig status` prints this rig's, `mcgyvr rig
peers` the ones pinned here, and the hub shows each rig's on its rig page and
in a session's members. After a peer's owner rotates its key, `mcgyvr rig
peers --forget <rig-id>` drops the old pin once you have compared the new
fingerprint with them. A peer from before identity keys sends none and is
taken as before, unpinned, and the rig logs each one it takes that way
("sent no identity key ... taken unpinned"). Against someone holding a rig's
token (not against the hub): once that rig's key is bound, the hub refuses a
hello from it that names none, so stripping the key cuts that rig off rather
than handing its peers no key.

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
changed answer), and it may send one sealed request again. The end of the
answer is not sealed: a hub that drops every event after the one carrying the
finish reason (today the trailing `usage` event) leaves an answer the rider
accepts without its counts. `mcgyvr rig rungs sync` says each rung's key id
(`sealed <kid>`), as the host's `rig up` does, so the two can be compared, and
notes a rung that was sealed and comes back keyless.

The host's agent holds an opened request to the bounds the hub holds one in
clear to (`hubwire.CHAT_MAX_*`, `MESSAGE_ROLES`, `CHAT_RANGES`), since the hub
cannot read it: a sealed request outside them ends `bad_seal` and reaches no
unit.

Python cannot clear what it freed: copies of a recent prompt and answer stay in
the freed memory of the rider's process and of the host's agent until it is
reused, sealed or not, so a memory dump of either reads them.
