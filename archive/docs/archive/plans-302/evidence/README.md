# Evidence pack — the #302 trunk review

The rule this pack obeys is lane/251's incident
(records/sessions/lane/251/2026-08-14-050514-adar.md): figures copied into bodies rot; a figure
without its derivation is not evidence here. **The evidence is `verify/`**: every figure there
sits beside the command (`uv run --no-sync …`, a `gh` read) or the records/ path that
re-derives it, verified against the pinned tree `main 4e110156`, 2026-08-17/18. `synthesis.md`
is the review's working narrative, not evidence — see its appended Derivation status block: a
figure quoted onward is taken from `verify/` or re-derived, never from the synthesis.

These files are records of the review as it was conducted, and records are history (ADR-0036
clause 4): quotations keep their original wording, and stale-at-reading facts get dated
corrections, never rewrites. Two consequences a reader needs:

- At review time two decision records were both numbered 0035; these files cite them the way the
  review met them. Since lane/304 (P0), **ADR-0035 resolves uniquely to the ceiling record
  (#262)** and the vocabulary record is **ADR-0036**. Where a file distinguishes the two it
  writes **0035a** (the ceiling record, #262) and **0035b** (the vocabulary record, #301 — now
  ADR-0036); a bare "ADR-0035" in these files carries its referent in the surrounding sentence.
- The review's intermediate subsystem maps stayed conversation-side and are not part of the
  record; every figure that survived into `verify/` carries an in-tree derivation instead.
  Synthesis figures sourced only to those maps are working notes, not evidence.

Contents:

- `synthesis.md` — the review's working synthesis: the state of the instrument at 4e110156,
  load-bearing facts with their sources, and the question list the verification pass attacked.
- `verify/` — the adversarial verification reports. Each claim carries a VERDICT
  (CONFIRMED / CORRECTED / REFUTED) and an EVIDENCE line with its re-derivation:
  - `commissioning-verdict.md` — is "5/6 done" honest; what r2 must re-purchase and its rig bill
  - `contradictions.md` — cross-checks of issue state, headers, and figure-to-record ties the
    plan leans on
  - `control-options.md` — ground truth behind the control choice: eligibility tables, contract
    fields, per-candidate reach
  - `process-mechanisms.md` — the process machinery verified in place: the four-lenses
    registry/canary pattern, body.py's verify mode, which drift vectors have checks
  - `r2-drain-list.md` — `product.py --check` reproduced and the moved-file enumeration behind
    Law 1's prediction
  - `retirement-premise.md` — the ADR-0020 retirement premise re-derived: the power/MDE
    arithmetic and the corrected contrast figures
  - `rig-reality.md` — srv1/srv2 ground truth: builds, models present, what was actually
    exercised live
  - `stats-defects.md` — the #263 statistics defects at tip (ablation pooling, redundancy CI)
    behind P2.4/P4.4
