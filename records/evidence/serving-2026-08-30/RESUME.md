# Resuming the 2026-08-30 concurrency run

18 cells measured, 6 outstanding. Everything needed to finish is committed.
This file is both the runbook and a prompt you can paste into a fresh session.

---

## Paste this

> Finish the 2026-08-30 serving concurrency run in this repo. Six cells are
> outstanding; 18 are measured and committed. Read
> `records/evidence/serving-2026-08-30/RESUME.md` first — it names the cells,
> the two traps that will silently corrupt a resume, and the exact commands.
> Start by running the status check in that file and tell me what it reports
> before you launch anything. Do not resume against a rig you have not just
> proven reachable: every one of the six losses came from measuring a host that
> had gone away, and the harness recorded some of them as `ok`.

---

## 1. Check the rigs BEFORE anything else

Both outages produced cells that looked measured and were not. Prove
reachability first, from this repo's host:

```bash
for h in srv1 srv2; do
  echo -n "$h: "
  timeout 12 ssh -o ConnectTimeout=10 -o BatchMode=yes "$h" \
    'echo UP; uptime -p; nvidia-smi --query-gpu=memory.used,memory.reserved --format=csv,noheader' \
    2>&1 | tr '\n' ' '; echo
done
```

Expect `UP`, and `17 MiB` used with `401 MiB` reserved on srv1 / `380 MiB` on
srv2. A timeout means stop — see §5.

## 2. Status check: what is actually done

`outcome: ok` is not sufficient on rows written before commit `d75d90fb`. Judge
the levels directly:

```bash
uv run --no-sync python - <<'PY'
import json, glob, importlib.util, sys
spec = importlib.util.spec_from_file_location("sr", "tools/bench/serving/run.py")
m = importlib.util.module_from_spec(spec); sys.modules["sr"] = m; spec.loader.exec_module(m)
for host in ("srv1", "srv2"):
    cfg = json.load(open(f"tools/bench/serving/configs/srv-lcpp-n1248-{host}.json"))
    last = {}
    for line in open(f"records/evidence/serving-2026-08-30/lcpp-{host}.jsonl"):
        if line.strip():
            r = json.loads(line)
            if r.get("label"):
                last[r["label"]] = r
    print(f"\n=== {host} ===")
    todo = []
    for label in [e["label"] for e in cfg["models"]]:
        r = last.get(label)
        if r is None:
            print(f"  {label:26} NEVER RAN"); todo.append(label); continue
        barren = m.barren_levels(r.get("concurrency") or {})
        if r.get("outcome") == "ok" and not barren:
            print(f"  {label:26} ok")
        else:
            ns = [b["n"] for b in barren]
            print(f"  {label:26} {r.get('outcome'):13} barren={ns or '-'}")
            todo.append(label)
    print(f"  -> {len(todo)} outstanding: {todo}")
PY
```

## 3. The six cells

| host | cell | why | action |
|---|---|---|---|
| srv1 | `m_dsv2-lcpp-srv1` | host lost power 137 s into n=2; n=2/4/8 barren | **drop row**, re-measure |
| srv1 | `m_gemma4-lcpp-srv1` | link died at n=8; n=8 barren | **drop row**, re-measure |
| srv1 | `m_q36iq2-lcpp-srv1` | never started | resume |
| srv1 | `m_oss20-lcpp-srv1` | never started | resume |
| srv2 | `m_kat-lcpp-srv2` | never started | resume |
| srv2 | `m_next-lcpp-srv2` | never started | resume |

All six are infrastructure losses. None indicates anything about a model or a
config.

## 4. Trap: two cells are stamped `ok` and resume will skip them

`--retry-failed` re-measures entries whose outcome is not `ok`.
`m_dsv2-lcpp-srv1` and `m_gemma4-lcpp-srv1` both read `ok` because they were
written before the barren-level downgrade landed (`d75d90fb`). **The fix does
not rewrite existing rows.** Drop them so `--resume` re-runs them:

```bash
cd records/evidence/serving-2026-08-30
cp lcpp-srv1.jsonl lcpp-srv1.jsonl.bak            # keep the record of the loss
python3 - <<'PY'
import json
keep = []
for line in open("lcpp-srv1.jsonl"):
    if not line.strip():
        continue
    r = json.loads(line)
    if r.get("label") in ("m_dsv2-lcpp-srv1", "m_gemma4-lcpp-srv1"):
        continue
    keep.append(line)
open("lcpp-srv1.jsonl", "w").writelines(keep)
print(f"kept {len(keep)} rows")
PY
```

Re-run the §2 status check afterwards and confirm both now read `NEVER RAN`.

## 5. Resume

Both rigs are independent machines; run them concurrently.

```bash
for h in srv1 srv2; do
  nohup uv run --no-sync python tools/bench/serving/run.py \
    --config  tools/bench/serving/configs/srv-lcpp-n1248-$h.json \
    --out     records/evidence/serving-2026-08-30/lcpp-$h.json \
    --journal records/evidence/serving-2026-08-30/lcpp-$h.jsonl \
    --resume --retry-failed \
    >> records/evidence/serving-2026-08-30/lcpp-$h.log 2>&1 &
done
```

Use `run.py`, never `sweep.py` — only `run.py` has resume (`run.py:319`, keyed
on `(host, label)`), and only `run.py` emits the schema this evidence uses.

Watch for the failure signatures, not just progress:

```bash
tail -F records/evidence/serving-2026-08-30/lcpp-srv{1,2}.log \
  | grep -E --line-buffered "concurrency ramp|ramp_failed|REFUSED|TimeoutError|URLError|Traceback|wrote records"
```

`TimeoutError` or `URLError` means the host went away mid-cell. Stop, fix the
host, drop the affected rows, resume. Do not let it keep writing.

## 6. Reading the results

The key is `tokens_per_s`, **not** `agg_tok_s`. `run.py` emits
`tokens_per_s` and `completion_tokens_total`; `sweep.py` names the same
quantity `agg_tok_s`. A reader using the wrong key sees `None` at every level
and reads a healthy run as dead. `per_stream = tokens_per_s / n` is exact.

`key = tokens_per_s x total_params`, per the run request.

**Anchor srv1's vLLM ladder at n=2, not n=1.** Its wall clock is flat from n=2
to n=8 while n=1 runs 2.5–3.2x faster per request, on all three models with
zero errors. Anchored at n=1 srv1 looks like it caps at 2.4–3.1x; anchored at
n=2 it scales 3.88x against a theoretical 4x. This is a real regime change, not
noise — the run request predicted it for one model and guessed wrong about why.

## 7. Done looks like

- §2 reports 0 outstanding on both hosts.
- `uv run --no-sync python -m pytest tests/ -q` is **green**. It is currently
  red on `test_the_recorded_run_measured_the_grid_it_was_asked_for`, by design:
  `m_dsv2-lcpp-srv1` holds a one-point curve. That red clears when the cell is
  re-measured and must not be silenced any other way.
- `ruff check tools/ tests/` clean.

## 8. What is already settled — do not re-derive

- **vLLM 7.37–7.67x** n=1→n=8, flat across 1.5B..7B. Complete, committed.
- **llama.cpp 2.22–2.74x** on card, **1.41–1.47x** offloaded.
- **CPU offload is the cause, not MoE.** `m_ling-lcpp-srv1` — a MoE small
  enough to stay resident on srv1's 6 GB card — scales 2.27x, like dense.
- **`--parallel` defaults to 4 slots**, which makes n=8 run as two batches of 4
  and produces a plateau indistinguishable from saturation. Every config sets
  `parallel 8`; `total_slots` is read back from `/props`. Assert it.
- **`-c` is total and divides across slots.** `-c 4096 --parallel 8` gives 512
  tokens/slot against a 475-token completion. The floor is 987/slot.
- **A card has four buckets:** `total = reserved + used + free`. The reserve is
  GSP firmware — 401 MiB srv1, 380 MiB srv2, fixed, not proportional. Weigh
  full-GPU cells against total-less-reserve.
- **`--cpu-offload-gb` is inert on vLLM for AWQ.** Three launches at 0/4/6 GiB
  each loaded 9.38 GiB and each OOMed. Do not treat it as a discount; a gate
  that did was written and removed the same day.
