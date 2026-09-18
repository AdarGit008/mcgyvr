# seccomp profiles a unit's launch may state

A unit of `fleet.yaml` may state `launch.seccomp`, a profile file in this
directory, named relative to the directory holding `fleet.yaml`. Both launch
paths apply it — lock-fleets' `_unit.sh` (`lockfleets.run_args`, as
`docker run --security-opt seccomp=<file>`) and the product's live path
(`mcgyvr emit`, which renders `security_opt` into the compose file and writes
the profile beside it). A unit that states none gets docker's default profile.

**Why the file travels with the compose file, and not to the rig.** Both
clients read the profile themselves and send its JSON to the daemon; neither
ships a path. `docker run` reads it with no path resolution at all
(`docker/cli`, `cli/command/container/opts.go`, `parseSecurityOpts`:
`os.ReadFile(v)`), so lock-fleets hands it an absolute path — and under the
door the docker CLI runs on the operator's machine, against the rig's daemon
over `-H ssh://<rig>`, so that is the file it reads. `docker compose` resolves
it against the **project directory**, which is the compose file's own
(`docker/compose`, `pkg/compose/create.go`, `parseSecurityOpts`:
`os.ReadFile(p.RelativePath(con[1]))`), so `emit` writes the profile next to
the compose file it names and states only the file name. Nothing has to be
installed on a rig, and a stated profile that is not there is refused by name
before anything starts.

`_move.sh` is the exception and refuses. Its stopwatch is one ssh whose docker
verbs are words the rig's own shell runs, so the client is the rig's and a path
on the operator's disk is not one it can read.

## `io-uring.json`

**Base:** docker's default seccomp profile, `seccomp/default.json` of
[moby/profiles](https://github.com/moby/profiles) at commit
`3c28324314729dbade8287e868eef6338c42807a` (the module moby vendors as
`vendor/github.com/moby/profiles/seccomp/default.json`). The base bytes hash
`sha256:536529b665dd0972c37bfb569f5d4ac8a53592e7b00752bc39ff063ca9864c74`;
`defaultAction` is `SCMP_ACT_ERRNO` over 442 allowed syscall names in 33
blocks. Fetched read-only; nothing here was edited in place.

**Added:** one appended `SCMP_ACT_ALLOW` block, and nothing else:

- `io_uring_setup`
- `io_uring_enter`
- `io_uring_register`

Those three are the whole difference — `tests/test_a_unit_states_the_seccomp_its_engine_needs.py`
holds the file to its base by digest with that last block dropped. Moby's
default does not list `io_uring_enter2`, so it is not added either. This is
**not** `seccomp=unconfined` and **not** `--privileged`: everything docker's
default refuses, this refuses.

**Why:** moby `891241e7e7` (2023-11-02, "seccomp: block io_uring_* syscalls in
default profile") removed the io_uring syscalls from the default profile. The
Lidenburg llama.cpp fork at `e85e4d9` gives its MoE expert cache an io_uring
disk tier, and `ggml/src/ggml-backend.cpp` L565-578 prints
`[expert cache] io_uring_queue_init failed: ...` and then calls `abort()` —
there is no fallback, and no environment variable disables the tier
(`GGML_EXPERT_CACHE` / `GGML_EXPERT_RAM_CACHE` are compile-time defines;
`GGML_EXPERT_CACHE_MAX` and `GGML_EXPERT_RAM_CACHE_MAX` only set sizes). So
under a plain `docker run` the call returns `EPERM` and the server dies before
it serves.

Only `srv2_35b_256k` states it. Any other unit that needs it states it too, or
launches without one.
