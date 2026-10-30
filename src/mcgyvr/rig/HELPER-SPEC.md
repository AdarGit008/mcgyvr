# mcgyvr-wg: what the rig agent expects of its WireGuard helper

The contract between the rig agent (this repository) and `mcgyvr-wg`, the userspace WireGuard
helper of a Mac or Windows rig's pooled sessions (its own repository). The product side is
`mcgyvr.rig.wgpin` (the pin), `mcgyvr.rig.wghelper` (the driver and its strict reply parser) and
`mcgyvr.rig.userwg` (the session host that drives it). This document is normative: the field table
in section 4 is the grammar. `tests/fake_wg_helper.py` is a test double that speaks a subset of it
(it refuses what the product must never send; it does not prove every refusal the helper owes).
Proto 1 is the head-only grammar; workers (section 6) come with a later proto, or with additive
verbs.

## 1. Asset, tag and pin

- Repository: `adar/mcgyvr-wg` on Forgejo, mirrored to GitHub as `AdarGit008/mcgyvr-wg`; the product
  downloads from the GitHub mirror (`serving.release.DOWNLOAD_URL`).
- Tag: `v<major>.<minor>.<patch>` (the first release is `v0.1.0`). `wgpin.TAG` names it, once.
- One archive per system and architecture, the names `hubwire.HOST_OS` and `hubwire.HOST_ARCH` spell:

  | os      | arch           | asset                                    |
  |---------|----------------|------------------------------------------|
  | darwin  | arm64, x86_64  | `mcgyvr-wg-<tag>-darwin-<arch>.tar.gz`    |
  | windows | x86_64, arm64  | `mcgyvr-wg-<tag>-windows-<arch>.zip`      |
  | linux   | x86_64, arm64  | `mcgyvr-wg-<tag>-linux-<arch>.tar.gz`     |

  `wgpin.asset_name(os, arch)` makes the name; nothing else spells it.
- The archive holds the program `mcgyvr-wg` (`mcgyvr-wg.exe` on Windows), at its top or under one
  top folder (which `serving.release` drops). Nothing else is required in it.
- The pin is one `serving.release.Asset(name, bytes, sha256)` row per asset in
  `wgpin.RELEASE.assets`: `bytes` the archive's exact length, `sha256` 64 lowercase hex digits of the
  archive. Where the digests come from: the helper's own reproducible build (`go build -trimpath`,
  CGO off, pinned Go toolchain) run by whoever cuts the release, NOT the mirror's API alone (that
  would check the mirror against itself); the published archives (Forgejo release and the GitHub mirror's
  `assets[].size` / `assets[].digest`) are then downloaded and must match. Signing the archives
  (minisign or cosign) is an optional extra, as is Apple/Authenticode code signing.
- This repository ships with no rows yet: `wgpin.pinned_for(os, arch)` is false everywhere, so no
  rig offers a native session, and `wgpin.helper()` refuses with "no pinned mcgyvr-wg <tag>
  archive for <os> <arch>; a native pooled session needs it, and nothing unpinned is fetched".
- The helper's own tests cannot use example addresses from the overlay range 100.64/10: the
  private-word guard both repositories run refuses those literals; compute them, or use RFC 1918
  ranges.
- Supply chain for the helper repo: wireguard-go and gVisor netstack pinned in `go.sum`; a
  `govulncheck` gate in its CI; a bump policy (security advisories within a week, else quarterly).

## 2. Process

- Started by the agent as `<program> session`, one helper per session, detached (hostos
  `popen_detached_kwargs`), and on Windows put in a kill-on-close Job Object by the agent.
- Environment: the agent passes only PATH, HOME/USERPROFILE, SYSTEMROOT/WINDIR, TEMP/TMP/TMPDIR,
  LANG/LC_ALL and `GOMEMLIMIT`; on Windows Go's `os/exec` also adds SYSTEMROOT to a child's
  environment when it is missing. The helper sets `RLIMIT_CORE=0` (darwin/linux) before it makes
  the key, so no crash dump can write it. Memory: gVisor's netstack buffers cannot be capped from
  outside (its stack is unexported), so the helper's memory is bound by `GOMEMLIMIT` and by the
  forward cap: at most 32 connections per helper, accepted and dialled ones counted together; a
  33rd is closed at once.
- stdin carries requests, stdout replies, stderr the helper's own log (the agent appends it to
  `logs/<tunnel container name>.log`, a 0600 file in a 0700 folder). Nothing but replies is ever
  written to stdout. Refusal lines on stderr are rate limited (at most one a second per forward).
- stdin EOF is `teardown`. A lapsed lease (section 4, `lease`; a monotonic clock) is `teardown` too,
  said on stderr as `lease ran out`. A request line that does not parse as one JSON object, or
  whose `id` is missing or not one greater than the last, is `teardown` with no reply (there is no
  id to answer); the agent reads the silence as a broken helper and ends it.
- Teardown ends every child: TERM to all children at once, one shared grace of 10 s, then KILL; the
  whole teardown fits inside the agent's 15 s (`wghelper.EXIT_S`), after which the agent kills the
  helper and ends what it recorded (it records each child's pid and start time). On Windows "TERM"
  is `TerminateProcess` on each child after the grace; the child's own descendants end when the
  helper's job closes. The helper puts itself in its own Job Object (KILL_ON_JOB_CLOSE and a process
  cap; no memory cap, since the job holds the head and its model) BEFORE writing the banner and
  never starts a child with CREATE_BREAKAWAY_FROM_JOB, so no child can outlive it (a nested job per
  part may come later). Then it closes every socket and exits 0.
- The helper never runs sudo, runas, netsh, pfctl or any firewall tool, never opens a TUN device and
  never needs admin rights.
- Key custody: the private key is born in the helper (`prepare`), is set only through wireguard-go's
  in-process `IpcSet`, and never leaves it: no UAPI listener is opened (no `ipc.UAPIListen`, no
  named pipe, so no `wg show` can read it), and it never appears on stdout, stderr, in a `why`, a
  child's environment or a file. In particular:
  - every `why` is fixed text the helper writes, never a wireguard-go or `IpcSet` error string;
  - the wireguard-go device logger runs at error level and never formats an `IpcSet` config;
  - the helper calls `debug.SetTraceback("single")` so a panic prints one goroutine's stack, not
    every goroutine's frames;
  - wireguard-go's `IpcGet` writes the key as hex into a pooled buffer while it answers; that is
    memory only, never written out, and the buffer is dropped; the helper calls `IpcGet` only to
    read peers and transfer counts, never to print it;
  - crash dumps: `RLIMIT_CORE=0` on macOS and Linux (no core file). macOS ReportCrash writes a
    stack report, not memory. Windows has no rlimit: the helper excludes itself from Windows Error
    Reporting dumps (`WerAddExcludedApplication` for its own program, per user, no admin) or, if
    that is refused, the residual is named in the release notes: a full user-mode dump configured
    by the machine's admin would hold the key.
- Children get no inherited pipe or handle of the helper's (stdin is the null device, stdout and
  stderr the log file named by `spawn`, opened to append without following a link: O_APPEND |
  O_NOFOLLOW, mode 0600 on macOS and Linux; FILE_APPEND_DATA with FILE_FLAG_OPEN_REPARSE_POINT on
  Windows, which has no O_NOFOLLOW).

## 3. Framing

- UTF-8 JSON, one object per line, `\n` terminated, at most 65536 bytes a line; no NaN or Infinity;
  no key given twice.
- On start, before reading, the helper writes one banner line:
  `{"id": 0, "ok": true, "helper": "mcgyvr-wg", "version": "<tag>", "proto": 1}`.
  The product refuses a helper whose `helper`, `proto` or `version` is not the pinned one.
- Request: `{"id": <n>, "verb": "<verb>", ...fields}`; `id` is a whole number 1..2147483647, one
  greater than the last. Fields are exactly those listed for the verb: a missing, extra or mistyped
  field is refused with `bad_request` and changes nothing.
- Reply: exactly one per request, in order, with the request's `id`:
  `{"id": <n>, "ok": true, ...result}` with exactly the result fields listed, or
  `{"id": <n>, "ok": false, "error": "<code>", "why": "<text>"}`, `why` printable, at most 300
  characters, holding no key and no secret.
- Error codes (a closed set for proto 1): `bad_request` (not of this grammar, including a `part`
  that is not one of proto 1's parts), `bad_state` (the verb is out of order, e.g. `up` before
  `prepare`, `stun` after `up`, `prepare` or `up` twice, `spawn` of a running part), `bind_failed`
  (a socket could not be bound), `no_answer` (`ping`: the host answered no small ping),
  `unknown_part` (a valid part that was never spawned, for `kill` only when the helper chooses to
  say so; `state` answers `absent` instead), `spawn_failed`, `internal`.
- The product parses strictly: a reply with another `id`, a missing or extra key, a key twice, a
  mistyped value (`true` is not a number), a value out of range, a port that is not ASCII digits
  without a leading zero, or a line that is not one JSON object is not believed: the helper is ended
  and the step fails (`tunnel_failed` while the session prepares or its tunnel comes up,
  `start_failed` while its head starts, `upstream_failed` once it is ready; a failed `peers`, `ping`
  or `transfer` during the walk or the watch counts as no answer from that peer).

Value shapes: `ipv4` dotted quad; `port` 1..65535 (0 only where said); `key` a WireGuard public key
(`sessionwire.WIREGUARD_KEY`, 44 base64 characters); `cidr` `ipv4/prefix` in canonical form;
`token` 32 lowercase hex.

## 4. Verbs (proto 1)

Order: `prepare` once first; `stun`/`keep` only before `up`; `up` once; `aim`, `peers`, `ping`,
`transfer`, `forward` only after `up`; `spawn`, `state`, `kill`, `lease` any time after `prepare`;
`teardown` last. Proto 1 has the part `head` only; workers add `worker-<n>` and `serve` (proto 2, or
additive verbs in proto 1 with the banner's version saying so).

| verb       | request fields                                  | ok result fields                  |
|------------|-------------------------------------------------|-----------------------------------|
| `prepare`  | `listen_port` port>=1024, `hosts` [ipv4] 1..8,  | `public_key` key                  |
|            | `lease_s` 1..3600                               |                                   |
| `stun`     | `token`, `servers` [[ipv4, port]] 1..2,         | `rtts` [[ipv4, port, us]] 0..2    |
|            | `attempts` 1..10, `wait_ms` 1..10000            |                                   |
| `keep`     | `token`, `servers` as `stun`, `every_s` 1..300, | (none)                            |
|            | `for_s` 1..86400                                |                                   |
| `up`       | `address` cidr, `mtu` 576..1420, `peers`        | (none)                            |
|            | [{`key`, `host` ipv4 or null, `port` 0..65535,  |                                   |
|            | `keepalive` 0..65535, `allowed` [cidr] 1..4}]   |                                   |
|            | 1..15                                           |                                   |
| `aim`      | `peers` [{`key`, `host` ipv4 or null, `port`    | (none)                            |
|            | 0..65535, `exact` bool, `moved` bool}] 1..15    |                                   |
| `peers`    | `pokes` [ipv4] 0..15                            | `now` epoch s, `peers` [{`key`,   |
|            |                                                 | `handshake` epoch s or 0,         |
|            |                                                 | `endpoint` "ipv4:port" or null}]  |
| `ping`     | `host` ipv4, `size` 1..1420, `count` 1..10      | `rtt_ms` number 0..1e9 or null,   |
|            |                                                 | `full` bool, `size` (the request's)|
| `transfer` | `pokes` [ipv4] 0..15                            | `peers` [{`key`, `rx`, `tx`}]     |
| `spawn`    | `part`, `program` absolute path, `argv` [str]   | `pid`, `start` (the start-time    |
|            | 0..256, `env` {str: str} 0..512, `cwd` and      | token, ASCII digits, 1..20)       |
|            | `log` absolute paths                            |                                   |
| `forward`  | `part`, `to` "ipv4:port", port>=1024            | `port` 1024..65535 (127.0.0.1's)  |
| `state`    | `part`                                          | `state` running/exited/absent,    |
|            |                                                 | `exit` int or null                |
| `kill`     | `part`                                          | (none)                            |
| `lease`    | (none)                                          | (none)                            |
| `teardown` | (none)                                          | (none), then the helper exits     |

What each verb does:

- `prepare`: refuse (`bad_request`) any host that is unspecified, loopback, multicast or the
  limited broadcast 255.255.255.255 (a subnet's own broadcast address is not known to the helper,
  and binding one fails `bind_failed`);
  generate a curve25519 key; bind ONE UDP4 socket per host in `hosts` on `listen_port` (never the
  wildcard, never IPv6); start the lease. The socket's source allowlist starts empty. DF
  (IP_DONTFRAG / IP_DONTFRAGMENT) is set on the session's sockets here, for their whole life, so
  every outer packet (WireGuard's too) is sent unfragmented and the `ping` full-size probe measures
  the path the tunnel uses.
- `stun`: send `udpwire` binding requests (format and vectors: `hubwire_schemas` `x-udp`) from the
  session socket to each server, `attempts` times, `wait_ms` apart; answer the round trip in
  microseconds of each server that answered, the least per server. The servers join the allowlist
  until `up`.
- `keep`: send a binding request to each server every `every_s` for `for_s` seconds; `up` stops it.
- `up` and `aim`: a peer with a `host` must have a `port` of 1..65535; a host with port 0 is
  `bad_request` (port 0 goes only with a null host).
- `up`: refuse `bad_request` when two peers' `allowed` overlap, or one contains this end's own
  `address` (wireguard-go's AllowedIPs would silently give the range to the last peer). Create the
  netstack with `address` (fixed from here) and `mtu`, bring the WireGuard device up on the same
  socket with the peers: endpoint `host:port` when `host` is set, `allowed` as their allowed IPs,
  persistent keepalive `keepalive` (0 = off). The allowlist is REPLACED by each peer's endpoint host
  (any source port); the STUN servers leave it. The netstack answers ICMP echo on `address` only,
  forwards nothing between peers and listens on nothing until `forward`/`serve`.
- `aim`: per peer, its allowlist entry is REPLACED by its `host` (and its `port` too when `exact`;
  no entry when `host` is null); its WireGuard endpoint moves to `host:port` only when `moved`.
- `peers`: one echo request to each poke (parallel, waited for, results ignored), then each peer's
  latest handshake and current endpoint. Keys are written base64, never UAPI hex.
- `ping`: the probe's shape is fixed by proto 1 and mirrors the Linux tunnel's `PING_SCRIPT`: one
  echo of 56 bytes must be answered within 2 s, else `no_answer`; then 5 at 0.2 s give `rtt_ms`
  (their mean, null when none came back); then `count` echoes of `size` bytes (the agent passes
  `pooled.TUNNEL_MTU - pooled.PING_HEADERS` and `pooled.FULL_PINGS`): `full` is whether any came
  back. `size` in the reply is the request's, and the agent refuses a reply naming another.
- `transfer`: pokes as `peers`; then each peer's received (`rx`) and sent (`tx`) bytes.
- `spawn`: start the child with argv `[program, *argv]`, exactly `env` as its environment, `cwd`,
  stdin the null device, stdout and stderr appended to `log`, as the helper's child, inside the
  helper's Job Object on Windows. One live child per part. Two promises the agent relies on:
  - the child leads its own process group (`setpgid(0, 0)` in the child, so pgid == pid): the
    agent ends a head left behind with `killpg(pid)`;
  - the child exists when `spawn` answers, and the reply carries its `start`: the token
    `mcgyvr.hostos.process_start_time` reads for that pid on this system (Linux: field 22 of
    `/proc/<pid>/stat`, clock ticks since boot; macOS: `ps -o lstart=` read in the C locale and
    UTC, as whole epoch seconds; Windows: `GetProcessTimes` creation time in 100 ns units), read
    by the helper while it still holds the child, so a pid reused after the child's immediate
    death is never recorded as the child.
  The child is started with no inheritable socket or handle of the helper's (close-on-exec on every
  helper descriptor; on Windows an explicit handle list with no sockets in it).
- `forward`: refuse `bad_request` at the request when `to`'s address lies in no peer's `allowed`
  or is this end's own address. Then bind TCP `127.0.0.1:0` and answer its port (>= 1024). For
  each accepted connection (within the cap of section 2),
  before any byte is read or dialled, find the CONNECTING (client) socket by direction: local
  `127.0.0.1:<the accepted connection's remote port>`, remote `127.0.0.1:<the forward's port>`, in
  ESTABLISHED state only. Accept only when exactly one live socket matches that tuple and it belongs
  to the spawned part:
  - macOS and Linux: the socket is in the part's OWN fd table (macOS `proc_pidinfo` /
    `proc_pidfdinfo` with `PROC_PIDFDSOCKETINFO` over the part's pid, same user, no root; Linux the
    `/proc/net/tcp` inode found among `/proc/<pid>/fd` links of the part), and the part's pid still
    has the start time `spawn` recorded;
  - Windows: `GetExtendedTcpTable` with `TCP_TABLE_OWNER_PID_CONNECTIONS`; the row's owner pid is
    the part's pid with the recorded creation time (rows name only the creating pid, which is why
    the part is spawned with no inheritable socket: no other process can hold a socket it made).
  Refuse — close the connection, say so on stderr (rate limited) — when the part was never
  spawned, has exited or was killed, when no row or more than one live row matches the tuple, when
  the owner is anything but the part, and when any lookup fails (fail closed). "Held by no other
  process" is not checked separately (macOS cannot see other users' fd tables without root); the
  rule is the positive one above. ESTABLISHED-only can race a client that half-closes before the
  lookup (its row turns FIN_WAIT); llama.cpp's rpc client does not half-close, and such a
  connection is refused, never accepted. An accepted connection is dialled to `to` through the
  netstack only.
  If the owner check cannot be made reliably on an OS, `forward` fails `internal` and that OS stays
  without native pooled sessions.
- `state`: the part's child: `running`, `exited` (with its exit status), or `absent` (never spawned
  or killed).
- `kill`: end the part's child (TERM, grace, KILL) and close its forwards; an absent part is ok.
- `lease`: renew the lease set by `prepare`.
- `teardown`: answer, then end everything (section 2) and exit 0.

## 5. What the agent sends (proto 1)

`prepare` (listen port = the session's tunnel port, hosts = the rig's `endpoints`, which a native
rig must name; lease = `Timing.lease_s`); `stun`/`keep` only when the rig lists `traversal` (a native rig
does not list it on Mac/Windows until a reply to the helper's own UDP is known to pass the host
firewall unasked); `up` from `tunnel.TunnelPlan` (mtu `pooled.TUNNEL_MTU`);
`aim`, `peers`, `ping` and `transfer` from the walk and the head's watch; one `forward` per rpc
device, then `spawn` of `head` (the pinned llama-server, `--host 127.0.0.1`, `--rpc` naming the
forwards, an environment of PATH-like variables plus `GGML_*`/`CUDA_*`/`VK_*`/`MTL_*`/`METAL_*`,
the card variables, and always `GGML_RPC_NO_COMM=1` and `GGML_RPC_NO_RDMA=1`, so the head never asks
a worker for comm_init's wildcard listener and never negotiates RDMA); `state`/`lease` while it
runs; `kill` and `teardown` at the end. Every tunable of the session (ports, lease, MTU, probe
size and count, STUN attempts and wait, keep-alive timing) is passed in; proto 1 fixes only the
probe's small-ping shape and the teardown grace.

## 6. Before native workers ship

- A native rpc worker binds the session's tunnel address inside the netstack only (`serve`), never a
  host address and never 0.0.0.0; its engine (`ggml-rpc-server`) listens on 127.0.0.1 and the
  helper dials it only after checking the listener belongs to the spawned worker's pid.
- Done: `emit._locked_native` reads the locked block's `role`; a locked native rpc worker
  renders the rpc-server block bound to the IPv4 literal its `-H` states, which
  `llamacpp.worker_may_listen` must allow (an address of a private or overlay network), and a
  locked native head keeps 127.0.0.1 (tests in
  `test_a_native_unit_is_emitted_as_a_program_not_a_container.py`). A pooled native worker's engine
  is NOT such a block: it listens on 127.0.0.1 behind `serve` (above), so if the worker work reuses
  `emit.native_block` for it, it needs an explicit loopback case, not the fleet rule.
- A per-session `--api-key` for the head's loopback API needs the agent's relay to send
  it. It MUST land before the first pin row: a pinned helper makes the native head reachable by
  any local process on the loopback, and the key is what keeps another local user off it.
- `rpc_server::comm_init` (llama.cpp b11960, `ggml/src/ggml-rpc/ggml-rpc.cpp`): with rank 0 it
  calls `create_server("0.0.0.0", request.port)` on a client's command, with the port the client
  chooses and nothing gating it (read at b11960; re-read it at every pin bump). A
  Linux pooled worker is contained by its tunnel netns and nft; a native worker is not: `-H` alone
  cannot hold the bind rule. It must be closed before any native worker ships, by one of: a pinned
  build where comm_init cannot open a listener (upstream gate, or a build flag that compiles it
  out), or `serve` parsing the RPC command stream it forwards and refusing the comm_init command
  (closing the connection) before it reaches the engine. Prove whichever is chosen with a test that
  sends comm_init through `serve` and finds no new listener. The agent's own heads already never
  send it (`GGML_RPC_NO_COMM=1`, section 5), but a worker must hold against any client, not only
  this agent's heads. The same hole exists for native fleet
  rpc units (`-H <LAN address>`), which are not behind any tunnel.
- `transport-apple.cpp` (`apple_rdma`, a caps-negotiated upgrade in b11960): a Mac head with a Mac
  worker could move RPC off the forwarded TCP onto a transport the helper does not see. The worker work
  must prove the upgrade cannot be negotiated through a netstack forward (e.g. the forward strips or
  refuses the capability) or turn it off (build flag or runtime option), with a test. The agent's
  heads run with `GGML_RPC_NO_RDMA=1` (section 5), which keeps their connection caps empty.
