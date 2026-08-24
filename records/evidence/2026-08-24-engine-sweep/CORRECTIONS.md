# Corrections (dated, appended)

## 2026-08-24 20:33 — srv1 control bar was mis-set; blocks (b)/(d)/R1 re-run

Rule (e)1 for E1-1 required >= 265 tok/s at n=32. That bar was derived from yesterday's srv1 MAXIMUM
(294.7, which occurs at n=256), not from yesterday's n=32 reading. Yesterday's no-eager len-1024
cells on srv1 read 229.3 / 229.8 / 230.9 at n=32 (records/evidence/2026-08-24-config-sweep/srv1-1.5B-stage2.jsonl);
today's E1-1 read 229.7 at n=32 and 44.2 / 27.5 / 107.0 at n=1/2/8 against 41.9 / 27.3 / 108.2 yesterday.
The control REPRODUCES; the rig state did not change. The runner's skip of B1-1, D1-1, D1-3, D1-4, D1-2,
D1-5 and R1 (rows with reason "rule (e)1") is therefore void. Those cells are re-run at 20:33 with
`--only`, appending to the same rows.jsonl and srv1.log. The skipped rows are kept as written.
Correct bar for E1-1 at n=32 would have been >= 207 (0.9 x 230).

## 2026-08-24 20:38 — LMDeploy cells refused on an "incomplete snapshot"; launch corrected, block (d) re-run on both rigs

Every LMDeploy launch exited after ~8 s and `--rm` erased its log (the mechanism #352 records). Reproduced by
hand on srv1 without `--rm`: `huggingface_hub.errors.IncompleteSnapshotError` — the cached checkpoint lacks
`.gitattributes`, `LICENSE`, `README.md` (vLLM's download skips them) and with `HF_HUB_OFFLINE=1`
`snapshot_download` refuses the hub id. Fix in runner.py `docker_run_cmd` (lmdeploy branch): pass the local
snapshot directory (resolved on the rig at launch) as `model_path`, keep the hub id as `--model-name` so requests
are unchanged, and drop `--rm` so a dying container keeps its log (teardown already does `docker rm -f`).
Rows for D1-1 (refused), D1-3/D1-4/D1-5 (skipped by rule (d)3) and the srv2 D2-* refusals that follow are KEPT;
the corrected cells are appended by `--only` re-runs (srv1 D1-1,D1-3,D1-4,D1-2,D1-5,R1; srv2 D2-1,D2-4,D2-5,
D2-6,D2-2,D2-7,D2-3,D2-8,R2) started automatically after each rig's first run exits. The srv2 first run still
holds the unpatched runner in memory, so its D2-* rows record the refusal a second time.

## 2026-08-24 20:40 — the incomplete snapshot is srv1-only; srv2 block (d) ran on the original launch

srv2's D2-1 launched and served (191.7 tok/s at n=1) with the hub id under `HF_HUB_OFFLINE=1`: srv2's cached
snapshot is complete. The queued srv2 `--only D2-*,R2` re-run was cancelled before it started (nothing appended).
Only srv1's cells run on the corrected launch (local snapshot path + `--model-name`).

## 2026-08-24 20:47 — srv2's 7B and 3B checkpoints are incomplete snapshots too; D2-2, D2-7, D2-3, D2-8 and R2 re-queued

D2-2 (7B) exited after ~9 s on both launch variants under the unpatched runner still in memory; the 20:40 note
was too narrow — only srv2's 1.5B snapshot is complete. D2-7 (7B), D2-3 and D2-8 (3B, rsynced from srv1) fail the
same way. Those rows are KEPT as refusals; the same cells plus R2 are appended by a `--only` re-run on the
corrected launch, started automatically when srv2's first run exits.

## 2026-08-24 21:35 — `srv1/run.json` and `srv2/run.json` renamed to `runner-run.json`

`tests/test_run_contract.py::test_a_one_armed_cell_is_stored_and_checked_like_any_other` is an `xfail(strict)`
whose only assertion is `records/evidence/*/*/run.json` existing — the one-directory-per-cell shape the run
contract defines and nothing has produced yet (#335). The runner's per-rig summaries matched that glob by name
alone and turned the xfail into an XPASS on CI (`c69e62c7`, push and pull_request rows). They are runner
summaries, not cell records, so they are renamed out of the reserved name; contents unchanged.
