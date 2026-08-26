# Which reading can state sole-clientness — #353, measured 2026-08-23

Issue: #353 · Lane: `lane/286` · Host: **srv1** · Both engines, one at a time,
each released back to a 1 MiB card afterwards.

`dispatch_max_parallel` bounds the realised batch only if this run was the sole
client, and nothing in the tree established that. #353 named three candidate
routes and ranked them. This is what each one turned out to be.

## vLLM — `vllm:request_success_total` answers it

Server: `vllm serve Qwen/Qwen2.5-Coder-1.5B-Instruct-AWQ` on srv1 (pip
launcher), the shipped `q15-vllm-s8` serve block, started through
`vllm._start`. Ready in 196 s. `/metrics` scraped over ssh before and after
each step.

**Positive control — five inference requests:**

| counter | before | after | delta |
|---|---|---|---|
| `vllm:request_success_total` (summed over `finished_reason`) | 0 | 5 | **5** |
| `vllm:e2e_request_latency_seconds_count` | 0 | 5 | **5** |
| `http_requests_total{handler="/v1/completions"}` | 0 | 5 | **5** |

**Negative control — what does NOT move the counter.** Three calls each:

| endpoint | `http_requests_total` | `vllm:request_success_total` |
|---|---|---|
| `/health` | +0 | **+0** |
| `/metrics` | +0 | **+0** |
| `/ping` | +0 | **+0** |
| `/v1/models` | +3 | **+0** |

**Failed requests — one each:**

| request | HTTP | `http_requests_total` | `vllm:request_success_total` |
|---|---|---|---|
| unknown model name | 404 | +1 | **+0** |
| prompt over `max_model_len` | 400 | +1 | **+0** |
| malformed JSON body | 400 | +1 | **+0** |

**The harness's own capture — two full `observed.capture()` passes:**

| pass | `http_requests_total` | `vllm:request_success_total` |
|---|---|---|
| 1 | +7 | **+0** |
| 2 | +7 | **+0** |

Identical both times, and decomposed the same way each time: `/v1/models` +1,
`/is_sleeping` +1, `/is_paused` +1, `/get_world_size` +1, `none` GET 4xx +2,
`none` POST 4xx +1.

### What that settles

- **The reading does not perturb the counter it reads.** `/metrics` is not
  instrumented at all, and `capture()` moves `request_success_total` by zero.
  The arithmetic needs no correction term for the harness's own traffic.
- **`vllm:request_success_total` counts inference and only inference.** Every
  control-plane call moves it by nothing.
- **A request that failed at the API layer is not counted** — and that is
  correct for the question being asked, not a shortfall: a request that never
  reached the engine never entered a batch, so it cannot have changed the batch
  shape a re-run has to reproduce. `http_requests_total` is the broader view
  and catches those, which is why the constant for it is kept beside the one
  that is read.

## ollama — no counter exists, and the engine says so

Server: `qwen2.5-coder:1.5b` loaded through ollama on srv1; child
`llama-server … --port 40953 --host 127.0.0.1 … -np 1`, build `b1-9d77fa172`.

| surface | result |
|---|---|
| ollama `:11434/metrics` | **404** (both rigs, 2026-08-23) |
| `llama-server` `/metrics` | **501** — `{"message": "This server does not support metrics endpoint. Start it with \`--metrics\`"}` |
| `llama-server` `/props` → `endpoint_metrics` | **`false`** |
| `llama-server` `/slots` | **200** — answers |
| `llama-server` `/health` | 200 |

The endpoint is off because ollama does not pass `--metrics` when it spawns the
child, not because llama.cpp lacks one. That is a fact about reach, and it is
what the refusal records.

### `/slots` `id_task` was the other candidate, and it is refuted

`id_task` is monotonic, so it looked like a counter. It is not one — its
increment per request is neither 1 nor stable, on one server, one model, one
request shape:

| requests sent | `id_task` | delta | per request |
|---|---|---|---|
| 3 | 0 → 15 | 15 | 5.00 |
| 1 | 15 → 22 | 7 | 7.00 |
| 1 | 22 → 29 | 7 | 7.00 |
| 3 | 29 → 46 | 17 | 5.67 |

llama.cpp assigns task ids to internal work as well as to requests, and how
much internal work a request causes depends on cache state. So `id_task` can
say that the server did *something*; it cannot say how many requests that was,
and a count is what the subtraction needs. Recorded as refuted rather than left
as an open candidate.

## Route 3 was not attempted

Card sampling as a tell (#348's per-task SM clock and power) is listed in the
issue as indirect and not conclusive, and nothing here needed it. It is a hint
that would send a reader to look, not a statement about sole-clientness.

## Rig state after

srv1 released both times: `released: True`, `card_used_mib: 1`, no
`llama-server` children, no vLLM process. srv2 untouched.
