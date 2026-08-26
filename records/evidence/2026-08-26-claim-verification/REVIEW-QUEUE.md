# Post-session review queue

All 45 concepts in `okf/` are signed `human:adar` by bulk approval (2026-08-26) and
resolve `STRONG`. The signature is recorded in `approvals.json`, not in the files, so it
survives regeneration. This is the list of what to actually look at, ordered by how much
it would cost to be wrong.

To reject one after review:

```bash
python3 - <<'PY'
import json, pathlib
p = pathlib.Path("records/evidence/2026-08-26-claim-verification/approvals.json"); d = json.loads(p.read_text())
d["V1"]["decision"] = "no"          # -> status: deprecated, drops out of the trust gate
p.write_text(json.dumps(d, indent=1, sort_keys=True) + "\n")
PY
python3 records/evidence/2026-08-26-claim-verification/build_okf.py && okf-rag update --corpus "$PWD/okf"
```

## 1. Stale cross-references inside approved concepts (3)

The GPU crew superseded M5 late, so three concepts still argue against the *old* noise bar
(0.77% steady-state) rather than the standing one (2.6% across reloads on srv1). **Every
conclusion survives** — the effects are 0.10%, -17% and monotone respectively, all far from
2.6% — but the reasoning sentence is out of date.

- `serving/vllm/enforce-eager-cost` (V1) — srv1 block says "far inside srv1's own 5-10%
  run-to-run spread (M5)". M5 no longer says 5-10%.
- `serving/llamacpp/no-mmap-host-asymmetry` (L6) — srv1 block cites "quiet-box
  repeatability of 0.77% (M5)".
- `serving/llamacpp/n-cpu-moe-non-monotone-edge` (L5) — superseded block cites the same.

## 2. Two register errors the crews caught (fix `CLAIMS.md`, then regenerate)

- **L5 and L6 are `qwen3-coder-30b` Q4_K_M, not the 35B** the register says. The 35B's srv1
  floor is ncmoe 28 — a different curve entirely.
- **H5's srv2 figure has no thread count.** 24.3 GB/s at t=4 against 20.3 at the host's full
  t=20. The record should pin `OMP_NUM_THREADS` or the number does not reproduce.

## 3. The 12 partials — verdicts that are judgement calls

`L2` `L10` `L12` `L22` `M1` `M2` `V2` `V6` `V9` `V11` `V13` and `V1`. Each is "the direction
holds, the stated magnitude or scope does not". If you disagree with where a line was drawn
between `partial` and `verified`/`falsified`, these are where to look. `M2` and `V1` are the
two that carry weight downstream.

## 4. Four claims excluded as untested

`L7` (KV-q8_0 cost) · `L14` (context buys nothing) · `V12` (speculative decoding) ·
`M4` (offload is bandwidth-bound — needs turbo/RAPL changes the crews were forbidden to make).
They are in `CLAIMS.md` with no verdict and have no concept file.

## 5. One finding with no claim behind it

Every launch in this corpus passes `-ngl 99`, which disables b10481's automatic memory
fitter: `common_fit_params: ... n_gpu_layers already set by user to 99, abort`. **Nothing
here has ever measured what the engine would choose for itself.** That is not a defect in
any claim above — it is a hole in the sampling frame, and it deserves its own issue.

## 6. Tooling note

`okf-rag update` hashes the **body**, not the raw file, so flipping a signature in
frontmatter reports `ingested 0`. That is correct — the embedding is unchanged, and the
OKF side reads files directly so the trust gate is always current. Do not read `ingested 0`
after an approval as a failed re-ingest.
