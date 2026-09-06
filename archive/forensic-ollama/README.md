# forensic-ollama

What Ollama was to mcgyvr, why it was removed on 2026-09-06, and the
measurements that decided its design — kept because the design was *right for
its evidence*, and the next person who needs a second wire protocol should find
the reasoning rather than repeat the experiment.

Nothing here is read by the product. `archive/` is not on any import path and
no gate reads it.

## What is kept here

- `d7-campaign.json` — the 2026-08-19 D7 campaign's serving config, moved out
  of `tools/bench/serving/configs/` on 2026-09-06. All eleven of its model
  entries name this backend, so there was no half of it to keep: gutting it
  would have left an empty config, and the `_doc` keys on those entries are
  the only surviving statement of what E2 and E13 decided and why
  (`records/headers/2026-08-19-d7-campaign.json` says as much — its intent
  survived in three places and none of them was a record).
- `runner-ollama-excerpt.py`, `detect-conventions-excerpt.py` — the product
  code as it stood at removal.
- `bench-records.txt`, `removed-lines.txt`, `runner-cav01-excerpt.md`.

## What was removed

Ollama was mcgyvr's first backend. Removed from `src/` and `tools/` in full:

- `mcgyvr.pool.Protocol.OLLAMA` — the enum member every dispatch decision
  branched on.
- `mcgyvr.runner.OllamaRunner` — the native `/api/generate` client, and its
  entry in the runner map. Kept verbatim in `runner-ollama-excerpt.py`.
- `mcgyvr.availability` — the `Protocol.OLLAMA: "/api/tags"` probe path.
- `mcgyvr.detect` — the `("ollama", 11434, "ollama", "openai")` port
  convention, and the `binds_as` machinery that existed because of it. Kept in
  `detect-conventions-excerpt.py`.
- `mcgyvr.config` — `sources.*.api` no longer offers `ollama`.
- `mcgyvr.cli` — the emit port-contention exemption keyed on `api == "ollama"`.
- `mcgyvr.verify` — the `:latest` suffix and `ollama/` routing-prefix
  normalisation.
- `tools/runs/hosts.json` — the three `ollama.service` environment settings and
  the `systemctl restart ollama` that applied them.
- `tools/bench/serving/calibrate.py`, `pin.py`, `observed.py` — the ollama
  engine arm.

`removed-lines.txt` is every line naming Ollama in `src/` and `tools/`, with its
original path and line number, captured immediately before the removal.

## Why it was removed

Owner's ruling, 2026-09-06: **dead weight.**

The live ladder of 2026-09-05 is vLLM on srv2 (3B on :8001, 7B on :8002) and
llama.cpp on srv1 (Qwen3.6-35B-A3B offloaded, :8080). All three rungs are
OpenAI-compatible. No rung has been served by Ollama since.

The daemon on srv2 was stopped and `masked` the same day. Measured before it was
stopped: it held **0 MiB of VRAM** — `llama3.2:3b` was pulled but idle-unloaded —
and it was `enabled`, so it returned on every boot, holding port 11434 on a card
with **115 MiB free** beside two running vLLM engines (8570 + 3212 MiB of
12288). One request to that endpoint would have tried to load 2 GB next to a
live ladder.

The code cost more than the daemon did. A protocol nothing serves is a second
path through every dispatch decision that no test of the live ladder exercises,
and it had already gone wrong unobserved: `emit`'s port-contention exemption
tested `source.api == "ollama"`, a field that holds the *dispatch* protocol and
is therefore `openai` for every Ollama source a config could describe. The
exemption never fired. Two rungs behind one Ollama endpoint — the one shape
Ollama is good at — would have been refused as contending for a port they were
meant to share.

## The measurement worth keeping: #164 / CAV-01

This is the part that outlives the backend.

Ollama answers on two protocols at one port. Its native `/api/generate` is what
a default install offers and what most examples show. Its `/v1` is
OpenAI-compatible.

**CAV-01 measured the native path at 32.3% against a true 84.1%** on the same
model, same weights, same prompts. The gap was not the model. `/api/generate`
does not carry the fields the harness needs — the native path spells the output
cap differently, and truncation is reported through `done_reason` rather than a
`stop_reason` the reply parser reads.

The conclusion (#164) is protocol-independent and still holds:

> **How a backend is ASKED what it holds and how work is DISPATCHED to it are
> two questions, and the best answer to each is not always the same server.**

Ollama was the case that proved it: `/api/tags` enumerates what has actually been
pulled to disk, which no OpenAI-compatible `/v1/models` tells you — so it was the
better *ask*. And `/v1` was the better *dispatch*. That is why `detect` carried
both `api` and `binds_as`, and why `binds_as_for("ollama", "ollama")` returned
`"openai"`.

Anyone adding a second protocol should read `runner-cav01-excerpt.md` before
deciding that one field can carry both facts. It cannot, and the emit bug above
is what happens when a later reader assumes it does.

## Files here

| File | What it is |
| --- | --- |
| `removed-lines.txt` | Every removed line with its original `path:line` |
| `runner-ollama-excerpt.py` | `OllamaRunner` and its protocol wiring, verbatim |
| `runner-cav01-excerpt.md` | The module docstring arguing CAV-01 and #164 |
| `detect-conventions-excerpt.py` | `PORT_CONVENTIONS` and the `binds_as` reasoning |
