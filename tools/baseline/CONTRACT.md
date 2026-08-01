# CONTRACT — the plain-git twin

What the baseline V2 workflow expects of a repo, written so a human (or any agent)
can comply with **git alone** (C28). The `baseline` CLI automates this contract;
it never replaces it. Everything here is checkable — that's the point.

## The loop

- **Orient first.** Start a session with `baseline orient` (or read `records/` by
  hand: newest session log per lane, its `next:` line, open PRs/issues). Never
  reconstruct state from a hand-maintained status doc.
- **Log last.** End or pause a session by writing one session record (below).
  The `next:` you leave is what the next session's orient surfaces.

## Records — one unit, one file, append-only

All durable intent lives under `records/` (schemas in `schema/record.*.schema.json`):

| kind | home | form |
|---|---|---|
| session | `records/sessions/<lane>/<YYYY-MM-DD>-<HHMMSS>-<agent>.md` | frontmatter + prose |
| judgment | `records/judgments/JDG-NNNN.json` | JSON |
| claim | `records/claims/CLM-NNNN.json` | JSON |
| decision | `records/decisions/ADR-NNNN.md` | header lines + prose |

**Append-only:** never edit a committed record — write the next one. (REC-01
proves this from history: modify/delete/rename of a record is a finding, and a
blob-at-introduction comparison catches merge-hidden edits.)

### Session records (by hand)

Filename: `<YYYY-MM-DD>-<HHMMSS>-<agent>.md` (UTC, agent slug `[a-z0-9-]`) under
`records/sessions/<lane>/`, where **lane = branch name**. Collision-free by
construction — no counters, ever. Frontmatter (all required):

```markdown
---
record: session/1
lane: v2/m4b-jdg-ledger
agent: adar
started: 2026-07-11T15:00:00Z
---

## Did
what happened and why — the forensic tier: reasoning, not just actions

## Dead ends
what was tried and abandoned, so nobody retries it

## Left open
next: the one most useful next step
```

`## Left open` + `next:` is load-bearing — orient reads exactly that shape.
Prefer `baseline log -m "..." --next "..."` — it derives everything, validates,
and scrubs. Hand-written records are covered once the pre-push hook is installed
(`cp hooks/scrub-pre-push.sh .git/hooks/pre-push` per clone; engine: `baseline scrub`).

### Judgment records

A judgment is **dated, owned, scoped, reasoned, and it expires**:

```json
{
  "record": "judgment/1",
  "id": "JDG-0007",
  "kind": "risk-acceptance",
  "date": "2026-07-11",
  "by": "adar",
  "subject": "SEC-13",
  "reason": "why this is acceptable — exists in no diff",
  "review_by": "2026-10-01",
  "expected_state": { "descriptor.maturity": "prototype" },
  "tripwire": { "fact": "descriptor.maturity", "op": "ne", "value": "prototype" }
}
```

- **Kinds:** `sign-off` (satisfies a manual rule whose id is `subject` — the
  judgment ledger is the ONLY sign-off path since M7b (the legacy `signoff.json`
  read retired; MIGRATION.md re-mints surviving entries), and a **lapsed
  sign-off is not signed**; the **newest** sign-off per subject governs, so a lapsed newest
  is not rescued by an older unexpired record — re-judge) · `deviation` ·
  `risk-acceptance` · `break-glass`.
- **The machine contract:** `expected_state` is the world you assumed (mismatch =
  DRIFTED, re-look); `tripwire` is the condition that VOIDS the judgment
  (`fact op value`, ops `eq|ne|gt|lt|exists|absent`; fired = TRIPPED, act);
  `review_by` lapses it (EXPIRED). Fact namespace: `descriptor.*`,
  `planes.{tree,history,forge}.*`, `git.{branch,head,shallow}`, `today`.
  An unresolvable fact path is a surfaced finding, never a guess.
- **Numbering:** next free `JDG-NNNN` in the directory. Two lanes can collide on
  a number — git surfaces that as an add/add conflict at merge; **renumber the
  incoming record** and move on. Never reuse a number.
- Author with `baseline jdg new …`; evaluate with `baseline jdg check`
  (M6's reconcile runs the same evaluation on cron and files issues).

### Promotion (M7a): what blocks, and what unavailability does

Since M7a the deterministic lane/divergence/merge rules (FLOW-01..05, FLOW-07 ·
DIV-01..03 · MERGE-02) run at **blocker** under the multi-lane postures — a
blocker-severity DIVERGED row **keeps its DIVERGED verdict** and fails the run
(check's exit, admit's refusal leg (b)) without being flattened into a generic
FAIL. Their resolution paths ride the finding text: for a divergence, **reopen
the issue if the work is genuinely unfinished, or merge/close-and-prune the lane
if it is done** — a lane whose tip is already merged into the default branch
derives **COMPLETED** and is exempt (its closed anchor is agreement, not
contradiction). Ruled explicitly: promoted blockers keep `on_unreachable: skip`
— their gating power exists only where their facts are readable; the fail-closed
floor remains admit's command legs (staleness · DESC-03 · gating-source loss)
plus reconcile's detection. An unreachable forge never silently blocks a merge,
and never silently green-lights the facts it could not read — it SKIPs, labeled.
One carve-out, keeping M6a's promise: under the **JDG-only admission path** the
promoted blockers ride as findings but refuse nothing — the path's ruled shape
(judgment additions alone) precludes a session record, so a promoted FLOW
blocker there would re-close the relief valve. Staleness still refuses.

### Descriptor changes (DESC-03, ENFORCED since M6a)

A PR that touches `baseline.repo.json` carries a JDG **in the same PR** whose
`subject` is exactly `baseline.repo.json` (the descriptor filename — the one
constant the tool owns; FLOW-06's fix text and this page emit the same spelling,
and `admit` matches nothing cleverer than the exact string) and whose `kind` is
one of **sign-off · deviation · risk-acceptance** (pinned at M7a: break-glass is
outage relief with its own gate semantics — it never doubles as descriptor-change
approval; the two valves stay separate). Snapshot the new
posture in `expected_state` with a tripwire on the changed axis — that part is
craft, not machine-enforced. At admit, ANY descriptor change without that
same-range judgment is a **blocker refusal**; the *weakening* classification
(the schema's declared `x-strictness` ladders + gate-consumed set-rules) rides
the finding text — deterministic, and M7's per-axis policy seam. Tuning knobs
(`lease_ttl`, `staleness`, `lanes.families`, `engine_pin`) are posture-neutral.

### The two files — the separation is FINAL (re-ruled at M7)

`baseline.repo.json` (identity & posture) and `baseline.config.json` (tuning)
do **not** converge — ever. The split is load-bearing, not transitional: the
descriptor is the **change-controlled** file, read at the *target ref* by admit
(FS1 — that ref-read ignores fields a later schema dropped, so a schema
contraction never bricks admit against history; the worktree read stays strict)
and guarded by DESC-03's same-PR judgment; the config is the **free
worktree file** — paths, commands, thresholds — editable without ceremony.
Converging them would put every `doc_lag_days` tweak behind judgment ceremony
and rewrite FS1/DESC-03/schema/corpus to fix zero named failures. Revive trigger
(the one honest reopen): a demonstrated need for per-field change-control
granularity inside one file.

### Break-glass (FS5, ENFORCED since M6a)

A `break-glass` JDG is the **only** tool-side override of a fail-closed
`admit`/`reconcile` gate. It names its `gate`, it expires fast, and it **lands
on main via its own prior PR — it cannot ride inside the change it unblocks**
(admit honors it from the TARGET ref only; one riding the incoming branch
relieves nothing). It relieves **gating-source loss alone** — never staleness
(data-plane truth: re-derive) and never DESC-03 (whose relief is its own
same-PR judgment). The relief PR is landable whenever tree+history facts are
intact: a range that is nothing but schema-valid judgment additions carrying an
unexpired `break-glass (gate: admit)` takes the **JDG-only admission path** —
judged from tree+history alone, the forge closed and labeled, so the valve
never depends on the forge plane whose loss it typically relieves. (A git-plane
outage — no target, no history — falls to layer 0 below.) Solo-mode honesty: self-merge remains
possible; the control is audit-visibility + expiry, not multi-party
authorization.

**Layer 0, named:** a repo admin can always bypass branch protection — that
valve exists whether documented or not, so the discipline is documented
instead: bypassed or merged-while-red changes are detected by reconcile's
post-merge revalidation (M6b), which files the issue demanding the
retroactive break-glass JDG. The morning-after paperwork is the control.

### Admit binding — the three rungs

1. **Merge queue** (org-owned repos): admit on the merge ref with the inputs
   digest — deferred to V3; no repo in this project's reach can host one.
2. **Required check + "require branches up to date"** (public repos any plan;
   private needs a paid plan): the real merge-point binding — the up-to-date
   requirement forces re-derivation at the merge-relevant SHA.
3. **Private repo, free plan: nothing is bindable.** Admit is advisory there,
   and the honest guarantee is **detection, not prevention**: reconcile files
   the merged-while-red issue. No rung pretends to be a stronger one.

## The scrub gate

Every tool-written record is scanned before it exists (`src/scrub.mjs`):
**deterministic signatures block** (SEC-01 parity + JWT + fine-grained PAT),
**heuristics warn** (severity never exceeds certainty). A block is non-lossy —
the draft survives under `.baseline/cache/` (keep that path **gitignored**; the
tool warns if it isn't) and the exact rerun is printed. A false positive becomes
a dated judgment in `.baseline/scrub-allowlist.json` via `--allow <finding-id>
--allow-reason "..."` (one flag surface across `log` and `jdg`) — the allowlist
stores a content-derived hash, never the value.
Never bypass a block by hand-writing the file; rotate the secret or record the
judgment. Hand-written records get the same scan from the pre-push hook (once
installed) and REC-02 re-scans everything that landed (still warn — REC promotion
deferred by the M7 ruling; the write/push tooling gates block).

**Documented residual risk (C34):** the `--pushed` scan reads the allowlist from
the worktree, which may itself be uncommitted — the judgment doesn't necessarily
ride the push (REC-02 in CI is the backstop). `scan()` matches text shapes
decoded as utf8 — a UTF-16-encoded record is a known blind spot the delegation
layer (gitleaks-class scanners, server-side push protection) covers. And until
M6's `admit`, the FLOW posture gate reads the *worktree* descriptor, so a branch
that weakens posture can self-silence FLOW-06 — the base-ref read lands with
admit (FS1).

## Lanes (M5) — the plain-git twin

Everything `baseline lane` does is expressible in plain git; the tool adds the
gates, the labels, and the honesty — never a private data model.

- **Claim** = create the namespaced ref at origin, first push wins. The message
  needs REAL newlines (bash does not expand `\n` inside double quotes, so a
  literal-`\n` message mints a trailer-less lane — the exact thing the trailers
  prevent), so build it with `printf`:
  ```sh
  msg=$(printf 'claim lane/N: issue #N\n\nBaseline-Issue: #N\nBaseline-Agent: <agent>')
  sha=$(git commit-tree "$(git rev-parse origin/main^{tree})" -p "$(git rev-parse origin/main)" -m "$msg")
  git push origin "$sha:refs/heads/lane/N"
  ```
  The trailers are the declared `join_keys` — hand-typed claims MUST carry both
  or every downstream join lies.
- **Lease** = derived, never stored: freshness = **max(tip committedDate, PR
  updatedAt)** (FS10 as amended — GraphQL no longer carries `Commit.pushedDate`)
  vs `lanes.lease_ttl`; LIVE < ttl/2 ≤ STALE < ttl ≤ ABANDONED. Git-plane-only
  derivation (committer clock, no PR corroboration) is low-confidence and says so.
- **Reclaim** = an empty child of the observed tip under the NEW agent's trailer,
  pushed with `--force-with-lease=refs/heads/lane/N:<observed-tip>` (an exact CAS:
  any move mid-flight — work, rewind, deletion — must reject). Only a lane that
  DERIVES ABANDONED may be taken; a live takeover requires an unexpired
  `kind: deviation` judgment naming the lane (the `--jdg` hatch). The dated
  takeover record rides `records/sessions/<lane>/` like any session record.
- **The FLOW discipline by hand:** anchor lanes to issues (FLOW-01), write the
  session record on the branch (FLOW-02) with a filled `next:` (FLOW-03), keep
  branches in declared families (FLOW-04 — `lanes.namespace` + `lanes.families`),
  push the newest record before pausing (FLOW-05), don't squat dead lanes
  (FLOW-07). Family branches (`release/*`) owe only placement, not lane records.
  DIV findings (closed issue under an active lane, `next:` at a dead issue, a PR
  closing a closed issue) are contradictions to RESOLVE, not warnings to mute.

## Reconcile — the morning-after loop (M6b)

`baseline reconcile` revalidates the default branch on cron and files what it
finds as issues. **No writes to the repo or main, ever** — the issue tracker is
the whole write surface, and every filing is lifecycle-managed:

- identity: an HTML marker `<!-- baseline:<id>:<subject> fp:<hash> -->` plus the
  **`baseline` label** (filter/mute it in your own inbox — that's the designed
  affordance). Keep BOTH intact when editing a filed issue: removing the label
  drops the issue from the dedup scan (the next run files a duplicate), and
  anyone who can apply the label can plant a marker that absorbs a key's
  lifecycle — the label is a collaborator-trust surface, not a security boundary.
- transitions: absent→file · changed→comment (the fingerprint collapses shas,
  ages, and dates — an aging finding never re-comments) · cleared→close naming
  the sha (**only on positive re-evaluation** — a rule that SKIPped cannot clear
  its issue) · recurred→reopen the SAME issue when the close was reconcile's own
  (the marker carries a `bot-closed` stamp).
- **a human close is a judgment.** Close an advisory (engine-row) filing yourself
  and it stays closed — recurrence earns at most one comment on new content. The
  deterministic-integrity classes reopen over any close: an expired/tripped
  judgment, a landed secret, a merged-while-red demand.
- bounds: 10 creations+reopens per run; overflow rides ONE rollup issue that
  self-drains over subsequent runs. A truncated issue scan suppresses creates.

**Merged-while-red** (the layer-0 bypass's paperwork): reconcile sweeps the
newest merged PRs and reads their **head** shas' check runs — a check named
`*admit*` with conclusion `failure` on a merged PR files the demand for the
retroactive judgment. The convention is exact: the judgment's `subject` names
the **short (7) merge sha** —

    baseline jdg new --kind break-glass --gate admit --subject "<short-sha>" \
      --reason "why it merged red" --review-by <date>

The demand clears on the judgment's **existence** at the tip (a lapsed one does
not zombie-reopen the incident — its expiry is the sweep's own finding), and is
never auto-closed by the tip moving on.

**The binding law.** Findings bind to the sha they evaluated, so filings require
the working tree to BE the fetched tip, clean. Behind-but-on-the-line or dirty
degrades to a labeled report-only run (nothing filed, recipe printed); a HEAD off
the target line refuses. Exit 1 means **delivery failed** — including a clean run
that could not read the tracker (a dead cron must not stay green). Relief: an
unexpired `break-glass (gate: reconcile)` on the default branch — gate:reconcile's
one consumer — covers live outages only, never a replay-plan mismatch, and never
the `multi-lane-local` posture (which closes the write surface by declaration:
that's exit 2, not an outage).

**Demo/consumer wiring (specced, not discovered).** `baseline-reconcile.yml`:

    on:
      schedule:
        - cron: '17 5 * * *'   # GitHub may delay/auto-disable after 60d inactivity — OPS-07 checks the state; orient's headline is the backstop
      workflow_dispatch:
    permissions:
      contents: read           # top-level default stays read-only (SEC-11);
    jobs:                      # write scopes are granted per-job, below
      reconcile:
        runs-on: ubuntu-latest
        permissions:
          contents: read
          issues: write        # the ONE write surface reconcile has
        steps:
          - uses: actions/checkout@v4
            with:
              fetch-depth: 0              # full history: the sweep reads blobs at the tip
          - run: node <skill>/baseline.mjs reconcile --repo .
            env:
              GH_TOKEN: ${{ github.token }}   # unauthenticated gh rate-limits at 60/hr
    # exit 0 with findings is CORRECT (the tracker is the alert surface);
    # exit 1 means the cron itself is broken — that's the red worth having.

## Generated views (M6c)

A file whose first line is `<!-- baseline:generated <kind> — do not edit by
hand; regenerate: baseline gen <kind> -->` is machine-derived: **edit the
records it derives from, never the file** — the next regeneration replaces your
edit, and `gen --check` reds the CI until someone regenerates. `gen index`
never overwrites a file WITHOUT that marker (move it aside or pick a different
`--out`; do not paste the marker onto a hand-written file — that authorizes the
clobber the refusal exists to prevent). Wire `gen --check` as an **advisory CI
job**: visibly red, outside the required set, and never `continue-on-error:
true` — a green job with a buried failure pays the friction and destroys the
signal. On a vendor bump, regenerate views with the NEW vendored skill and
commit them alongside the bump.

## Admit provenance (M6c)

Every admit verdict carries its receipt: `provenance: inputs_digest <hash> ·
head → target · descriptor <blob-oid> · rules <version> · checks · anchor`.
Two runs with the same digest derived from the same world; any consulted input
moving — including a plane's availability — changes the hash ('not consulted'
is a digested VALUE, not a hole). Provenance never refuses, never warns, never
counts: it is the receipt, not a gate. V3's merge-ref binding is its intended
consumer; today it is the paste-into-the-PR-thread proof of what was judged.

## The vendored lock (M7c)

**Vendoring is the consumption model** — S9's `--vendor` flag never existed and
no installer ships; the manual copy IS the procedure: copy the toolkit's tool
files (SKILL.md's co-located list — at minimum `baseline.mjs`, `check.mjs`,
`rules.json`, `rules/`, `schema/`, `src/`, plus the shipped `.gitattributes`,
which keeps the hashed bytes EOL-stable on every platform) into
**`tools/baseline/`** (the canonical location — the one path REC-06
and the lock contract know), keep the repo-local `baseline.config.json` /
`baseline.repo.json` at YOUR root, then pin what you copied:

    node tools/baseline/baseline.mjs gen lock --repo .
    git add tools/baseline.lock.json    # commit the lock BESIDE the tree, same PR as the copy

`gen lock` writes `tools/baseline.lock.json` — exactly `{version, tree_hash}`:
the version from the *vendored tree's own* `rules.json`, the hash recomputed
over every vendored file (sorted paths, raw bytes, worktree semantics).
**REC-06** (warn, deterministic) compares on every check/reconcile run — *unpinned* (tree, no
lock), *skew* (hash mismatch, naming the lock's version and the tree's), or
PASS; no tree at the canonical path is a SKIP. A vendor bump and its re-pin
travel in ONE PR; regenerate generated views with the NEW tree in that same PR
(the `gen --check` remedy names this case). **OPS-07** (warn) closes the loop
at the forge: ONE recorded query of the reconcile workflow's state —
any non-`active` state fails the rule, named (`disabled_*` in practice —
GitHub's 60-day auto-disable is the death mode); no reconcile workflow in the tree is a SKIP, never wallpaper.

## Reserved (lands later, documented now)

- **V3 horizon:** the pointer-install consumption flip (revive: a second real
  consumer or escalating vendor-diff pain), merge-ref/digest binding (revive:
  a merge-queue-capable consumer), the per-axis descriptor-weakening policy
  (revive: the first contested weakening rubber-stamp).
