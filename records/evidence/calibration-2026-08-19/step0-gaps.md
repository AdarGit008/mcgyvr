# Step 0.1 — gaps and gotchas, resolved before the D7 campaign

Two scouts and a verifier, 2026-08-19. Scout A read the `local-ai` repo (context
only — nothing enters this repo as content) for what is known about srv1 and srv2;
Scout B read this harness for every assumption it makes about them; the verifier
tested 32 claims against both live hosts with read-only commands only. Nothing was
started, stopped or written on either rig.

## The rigs as they actually are, 2026-08-19

| | srv1 | srv2 |
|---|---|---|
| card | GTX 1660 SUPER, 6144 MiB, CC **7.5** (Turing) | RTX 3060, 12288 MiB, CC **8.6** (Ampere) |
| driver | **580.173.02** (CUDA 13.0) | **595.84** (CUDA 13.2) |
| RAM | 30 GB total, 26 available | 30 GB total, 28 available |
| disk free | 606 GB `/home`, 126 GB `/` | 517 GB `/` |
| ollama | 0.32.4, `User=ollama` | 0.32.5, `User=ollama` |
| `OLLAMA_NUM_PARALLEL` | **2** | **unset** (engine default) |
| `OLLAMA_MAX_LOADED_MODELS` | **3** | unset |
| `OLLAMA_KEEP_ALIVE` | **5m** | unset |
| vLLM | pip, `~/.local/bin/vllm`, 0.26.0, torch 2.11.0+cu130 | **docker only**, `vllm/vllm-openai:v0.26.0` |
| ollama models | 5 (the full srv1 roster) | 12 (9 of the 10-model roster) |

Both hosts booted within 5 s of each other (btime 1786645488 / 1786645483) — a
shared power event, which `pin.py`'s `boot_time` token will reflect on both at once
if it recurs.

## Blockers — these had to be resolved before the campaign

### B1 — `max_num_seqs` is on no vLLM 0.26.0 endpoint, so D1's `declared_slots` has no observed source for vLLM

The verifier searched the whole of `/server_info` (three top-level keys,
`vllm_config` 3,118 characters), `/v1/models`, and every env block on a **live**
server launched `--max-num-seqs 16`: `'num_seqs'` 0 hits, `'seqs'` 0 hits,
`'scheduler'` 0 hits. There is no JSON path.

**The trap, confirmed live.** `/metrics` carries
`vllm:cache_config_info{kv_cache_max_concurrency="16.001953125"}` on that server —
which reads as 16 and is *not* the flag. It is `kv_cache_size_tokens / max_model_len`
= 131088 / 8192 = 16.0018. Anyone spot-checking it today concludes it works, and it
would silently diverge the moment `max_model_len` or the KV allocation changed.

**Decision E5 — vLLM's `declared_slots` is dispatched, not observed.** D1 split the
output into `declared_slots` (a read) and `saturation_n` (a derivation). For ollama
that split holds: `total_slots` comes off the child's `/props`. For vLLM the
declaration exists only as the flag *we* passed. The field therefore carries a
provenance of `dispatched` for vLLM and `observed` for ollama, and vLLM's value is
sourced from the run's own `serve.max_num_seqs`, never from the server. A field that
says where it came from is the whole point of D1's split; a dispatched value
labelled as a read would be the same one-field-two-meanings defect D1 fixed, a level
further down. The `kv_cache_max_concurrency` coincidence is recorded here so nobody
"fixes" this by reading it.

### B2 — srv2 does not hold the checkpoint both vLLM entries serve

`configs/srv-full.json` serves `Qwen/Qwen2.5-Coder-1.5B-Instruct-AWQ` for
`q15-vllm-s8` and `q15-vllm-s16`. srv2's HF hub holds only the 14B, 7B and
Qwen3-4B AWQs. `run.py:101,123` runs every entry on every host, so both srv2 vLLM
entries would hit an **implicit download inside `START_TIMEOUT_S = 900`** — a cold
pull on the critical path, inside a container whose network path nobody measured.

**Decision E7 — pre-warm srv2's hub in step 0.2.** 1.61 GB, cheap, and it takes a
cold download off the critical path of an 8-9 h run. Not done in 0.1 because it is
not read-only.

### B3 — the harness cannot express the D7 roster

`run.py:100-123` is `for host in hosts: for spec in entries:` — a full cross-product
with no host affinity. The roster is **5 models on srv1 and 10 on srv2**; the
config cannot say so. The label `q15-ollama-srv1` reads like affinity and is not.

**Decision E6 — entries gain a `hosts` list; an entry runs only on the hosts that
name it, defaulting to all.** Without this the campaign either runs srv2's 10-model
roster against srv1's 6 GB card or does not run the roster at all.

### B4 — ollama's `llama-server` children are not the ssh user's to kill

`User=ollama, Group=ollama` on both hosts. `ollama.py:170`'s
`pkill -f '[l]lama-server'` runs as `adaramir` and gets EPERM on every match —
silently, because stderr is discarded and the step ends `; true`. Group membership
`982(ollama)` does not grant kill; kill needs a UID match.

The card *does* still clear, because the next step is
`sudo -n systemctl restart ollama` and passwordless sudo is confirmed on both. So
the release is effective and **the mechanism recorded in the run log is a lie**:
`own_processes_remaining` is computed from a `pgrep -c` that would have read 0 either
way.

**Decision E9 — the kill runs under `sudo -n` and its effect is asserted, not
assumed.** A cleanup step that cannot work, wrapped in a suppressor that hides that
it did not, is worse than no step: it is the D8 failure mode (a refusal recorded as
a success) inside the cleanup path.

### B5 — the documented `CUDA_HOME` launch fix was never real

`calibrate.py:261` sets `CUDA_HOME` to the literal
`$HOME/.local/lib/python3.14/site-packages/nvidia/cu13`, and `vllm.py:527` renders
env through `shlex.quote`, so `$HOME` never expands. Read straight off the live
server's `/proc/774452/environ`: `CUDA_HOME=$HOME/.local/...` — the literal string,
which `ls` cannot resolve. The *expanded* path does exist and 3.14 is correct today
(the only `~/.local/lib/python3.*`), but no process has ever seen a valid value.

This is the env block the calibration record credits with fixing "ten failed
launches" (README, *Harness defect*). It fixed nothing; the launches were fixed by
something else, and the server loads and serves without it.

**Decision E10 — drop `CUDA_HOME` rather than repair it.** Expanding it correctly
would introduce an untested variable into the launch path immediately before an
8-9 h campaign, and its effect is unmeasured precisely because it has never been
set. A broken literal that reads as a fix is worse than its absence. The README's
attribution of the ten-launch fix is corrected here.

### B6 — the docker `ancestor` filter works today, by a coincidence worth removing

`vllm.py:206,252` filters `--filter ancestor=vllm/vllm-openai` (bare, i.e.
`:latest`) while `_start` launches `:v0.26.0`. The verifier tested it empirically
against four real exited containers of exactly those tags: all four forms — bare,
`:v0.26.0`, `:latest`, and the image ID — match all four containers, because docker
resolves `ancestor` to an **image ID** and both tags are `ffb2d59b1c05`.

So `release()` does stop the container today. It stops working the moment a newer
`latest` is pulled, and at that point `vllm.py:268-278` reports `released: True` on
a container it never touched — which is the single highest-ranked silent failure
below.

**Decision E8 — filter on `CONTAINER_IMAGE`** (already a module constant at
`vllm.py:459`) in both places. One word, removes the coincidence.

## Silent-failure risks in the harness, ranked

These are Scout B's findings, ordered by what they cost if they fire during the run.

1. **`vllm.release()` can report success on a container it never stopped.**
   `released` is `pgrep -c '[v]llm serve' == 0` (`vllm.py:268-278`) — a
   containerised vLLM never matches that pattern. `run.py:130-145` trusts that flag
   as the **only** exclusion gate. Today `MIN_VRAM_FRACTION` catches the
   consequence downstream; **D4 removes that catch.** Fixed by E8 plus a card read.
2. **`card_idle_before_load` never reads the card and gates nothing.**
   `ollama.py:257` sets it from `release(host)["released"]` — ollama's own process
   count — and `check["ok"]` (`ollama.py:268-274`) never includes it. D4's stated
   justification for withdrawing the VRAM gate ("`claim` already checks
   `card_idle_before_load` separately, and that is the check that catches
   contamination") **is not true of the code as written.** `release()` already reads
   `gpu_used_mib`; it is simply unused. This must be made true in step 1, or D4
   withdraws a gate and replaces it with nothing.
3. **A partially-failed ramp level reads as a plateau.** `_level`
   (`contract.py:469-478`) divides *successful* tokens by *total* wall-clock and
   records `errors` that `knee`, `_throughput_plateau` and `_max_speedup` never
   read. Half the requests timing out at n=16 produces a lower number, not a
   refusal — i.e. a wrong `saturation_n`, which is the campaign's headline output.
4. **A missing `usage` block reads as zero throughput.**
   `usage.get("completion_tokens") or 0` (`contract.py:470`) turns "could not count
   tokens" into "does not batch".
5. **`contract.ssh` erases success, non-zero exit and timeout into one value** —
   `stdout or None`, every exception swallowed (`contract.py:192-201`).
6. **`ready` from `_start` is recorded and never asserted** (`vllm.py:566`), and its
   ssh budget (960 s) is shorter than the readiness loop it wraps (up to 1350 s)
   (`vllm.py:552-556`).
7. **`LOAD_TIMEOUT_S` (2400 s) is shorter than the remote `curl -m 3600` it wraps**
   (`ollama.py:103,247`): on a slow load the ssh gives up while the load continues,
   and attempt 2 issues a second clear-and-load on top of it.
8. **`snapshot.gpu_idle` and `gpu_compute_apps` are computed and never read**
   (`contract.py:230-237`) — a foreign process on the card is recorded and ignored.

## Gotchas carried in from local-ai

Operational facts measured on these two machines, none of which is in this tree.

1. **`/health` returns OK before the weights are on the GPU.** The check that works
   is `/health` **and** `nvidia-smi memory.used > 500 MiB`. The harness's
   `MIN_ALLOCATION_MIB = 500` is exactly this and must stay.
2. **Load-to-health is slow and variable** — their recorded waits ran 30 s, 45 s,
   120 s, and the gpt-oss scripts needed **up to 240 s**.
3. **vLLM stop does not free VRAM immediately** — their swap script polls 30 s for
   `< 100 MiB` and warns when it does not happen.
4. **The GPU does not return to idle by itself.** Documented cleanup is a `pkill` of
   `llama-server` plus a service restart, then a verified `memory.used < 100 MB`.
5. **ssh drops under load.** When a load or inference saturates the box,
   interactive ssh times out; their practice was `nohup` plus a log file and never
   holding a session across a load. (Decision E4.)
6. **`OLLAMA_NUM_PARALLEL` is queue depth, not batching** — measured 50/53/55/56
   tok/s at n=1/2/4/8 on srv2's 7b against vLLM's 68 -> 489 on the same box and
   model. Left unset it also reserves up to 4 slots' worth of VRAM for nothing.
7. **ollama's `num_ctx` defaults to 2048 and truncates the prompt silently**, and
   ollama then reports the *truncated* prompt count, so the probe looks clean. Our
   ramp prompt is short, so the exposure here is small — but `num_ctx` is set
   explicitly rather than assumed.
8. **Reasoning models eat the token budget.** gpt-oss burns ~52% of output on
   hidden `reasoning_content` even at low reasoning. `gpt-oss:20b` is on the srv2
   roster, so its `usage.completion_tokens` counts reasoning tokens: RAMP_TOKENS =
   475 buys roughly half that in visible output there. Throughput is still
   throughput; the field means something different for that one model and is
   labelled.
9. **Pin by digest, not by name.** srv2 carries `qwen3:30b-a3b` pulled as **F16
   instead of Q4** (18 GB, 59% CPU spill, HumanEval+ 3.7%), sitting next to the
   roster's `qwen3-coder:30b` in `ollama list`. "Present" is not "usable".
10. **srv1's vLLM is AWQ-on-Turing**: no FA2, no CUDA graphs (`--enforce-eager` is
    mandatory), PyTorch sampling, and a measured ~4x penalty against the same model
    under ollama on the same box. FP8 will not load on srv1 at all (needs CC >= 8.9).
11. **Two numbers not to reuse as baselines.** srv2's headline 489 tok/s
    @16-concurrent was measured under a config later withdrawn for OOMing, and every
    srv1 bandwidth and CPU-decode figure is pre-XMP and was never re-taken.

## What 0.1 could not test, deferred to 0.2 as assertions

Each needs a resident model, so 0.2.2 — which loads every roster model anyway —
carries them as assertions rather than as separate work.

1. `pgrep -af "[l]lama-server"` returns at least one line once a model is loaded.
2. Each line carries `--port <N>` **space-separated**, so `ollama.py:399`'s
   `re.search(r"--port\s+(\d+)")` matches. A switch to `--port=N` returns zero
   instances, and `claim` then fails the whole entry (`ollama.py:272`) with a
   message blaming VRAM placement.
3. The child's `/props` answers 200 with `total_slots` — the **only** source of
   `declared_slots` for ollama under D1 — and reads **2 on srv1** (`NUM_PARALLEL=2`)
   and **1 on srv2** (unset), matching what `observed.py:916` recorded 2026-08-18.
4. `fingerprint.classify` on the real `/props` config raises no `UnclassifiedError`.
   The four keys `ollama.py:348` lifts are in-vocabulary; the risk is
   `default_generation_settings.params`, which goes in wholesale at `ollama.py:346`.
5. `kill_servers` clears the child, or is honestly recorded as a no-op (B4).
6. `placed.fraction` on a real resident load — untestable with an empty card.
7. The vLLM ramp reads the knee at the launched width. Given B1 this is now the
   **only** verification that `declared_slots` matches reality;
   `observed.py:736-750` reports the srv1 knee at exactly 8 on a `--max-num-seqs 8`
   server, and it must be re-confirmed at 16.
8. The srv2 1.5B AWQ pre-warm completes (B2 / E7).

## What was verified and holds

ssh passwordless and BatchMode-clean on both; both bare names resolve on the client
via MagicDNS (the ssh_config bare-IP HostName for srv2 does not bind); ollama
answers 200 on the network on both; the unit is named `ollama` on both; passwordless
sudo on both; one GPU per host, so `contract.first_int` is safe; the pinned
`d7372fd8...` digest for `qwen2.5-coder:1.5b` is present and identical on **both**
hosts; `vllm` is on srv1's non-interactive PATH so the pip-vs-docker detection is
correct on both; torch 2.11.0+cu130 and safetensors import on srv1; the container
image carries `TORCH_CUDA_ARCH_LIST` including 8.6 and is proven to have reached
srv2's GPU; `/server_info` parses — `parse_repr` yields 33 keys, `classify` returns
31 semantic / 2 operational with **no `UnclassifiedError`**, and the fingerprint
computes; all 11 endpoints answer 200, and `/openapi.json` declares `/sleep`,
`/wake_up` and `/is_sleeping` as D7 item 5 needs; disk and RAM are ample on both.

## One thing the record got wrong

The handoff said "Both rigs are idle and nothing is running." srv1 was holding
**4954 of 6144 MiB** in a leftover `vllm serve Qwen2.5-Coder-1.5B-AWQ
--max-num-seqs 16` (pid 774452) started 06:07Z — the `q15-vllm-s16` instrument,
never shut down after the phase-3 ramps. It was **left up deliberately through
0.1** (decision E1) because it made every vLLM endpoint check above testable at
depth 0 without starting anything, and it is torn down in 0.2.3. srv2 was genuinely
idle.
