---
name: baseline
description: "Use when asked to run baseline, score a repo, check build- or project-readiness, audit a repo against a standard, or adopt/scaffold the project-baseline standard. Runs a zero-dependency Node checker (90 rules across build, tests, security & supply-chain, reproducibility, operability, change-governance, community, context/doc-drift, claims, records & ledger, lane workflow, and divergence), reads the scorecard, and helps fix or scaffold what's missing."
version: 2.5.0
author: Adar (AdarGit008)
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [baseline, readiness, ci, standards, project-quality, code-review]
    related_skills: [requesting-code-review, plan, systematic-debugging, test-driven-development]
---

# project-baseline

## Overview

A **testable readiness standard**: 90 rules, each backed by a check a zero-dependency Node runner executes on a repo *at rest*. Blockers fail CI (`exit 1`); the judgment calls a script can't make resolve via a dated **sign-off ledger**. The throughline: *don't trust a written promise — make something check it.* A checklist doc drifts; this is the checklist as an exit code.

Runs natively under **Hermes** and **Claude Code** (and any agent that loads `SKILL.md`). The runner is portable — plain Node, no agent-specific dependency. Source: `github.com/AdarGit008/baseline-skill` (reference repo: `baseline-demo`).

## When to Use

- "run baseline", "score this repo", "check build-readiness / project-readiness"
- "audit this repo against a standard", "is this build-ready?"
- "set up / adopt / scaffold baseline here"
- "fix the baseline failures", "get this to green"
- "what does SEC-03 check", "why did CTX-05 fail"

**Don't use for:** general logic/bug review (use a code-review skill) or writing tests (use a TDD skill). Baseline checks *readiness posture at rest*, not runtime correctness.

## Setup — resolve the toolkit path first

`$SKILL_DIR` = the absolute path of the directory containing this file. Resolve it to a concrete path before running anything (never pass the literal `$SKILL_DIR` to the shell). Typical locations:
- Hermes: `~/.hermes/skills/software-development/baseline`
- Claude Code: `~/.claude/skills/baseline`

The unified CLI is **`baseline.mjs`** — `node "<abs>/baseline.mjs" <command>` (`check`, `admit`, `reconcile`, `orient`, `lane`, `log`, `jdg`, `gen`, `scrub`, `help`); `baseline check …` delegates to `check.mjs`, still the checker. Both load the rule set (`rules.json` manifest + `rules/` modules) and `src/` from their own directory, so always invoke **by absolute path**; don't copy them away from the rule set + `src/`. Requires **Node ≥ 18 and `git`** on PATH — if `node` is missing, say so rather than guessing.

Co-located files: `baseline.mjs` (CLI entry: check / admit / reconcile / orient / lane / log / jdg / gen / scrub), `check.mjs` (the checker), `rules.json` + `rules/` (the rule-set manifest + the 90 rules, one module per category), `schema/` (the descriptor schema + the four record schemas), `CONTRACT.md` (the plain-git record forms), `config.example.json`, `templates/` (scaffolds), `config-presets/` (ready-made configs), `hooks/` (SessionStart orient hook + pre-push scrub hook), `REFERENCE.md` (full reference), `GLOSSARY.md` (term definitions).

## Orientation — the first act

Before working in a repo that runs multiple agent lanes (or at session start), **run `baseline orient` first** — a derived-state survey, so you never reconstruct state from a hand-maintained status doc (C16):

```bash
node "$SKILL_DIR/baseline.mjs" orient --repo <target>
```

- **Capability header** — which planes are reachable (tree / history / forge). Every unreachable plane degrades to a note, so orient works offline and never blocks.
- **Divergence first**, then **live lanes** (open PRs + each branch's latest session `next:`), **backlog** (open issues by milestone), and **this lane** (current branch + its `next:`).
- It's an *agent helper, never a gate*: read-only, `gh`-based, exits 0 even degraded — `--strict` turns forge-unreachability into exit 1; `--json` for machine use.
- **Install it as infrastructure:** wire `hooks/orient-session-start.sh` into Claude Code's `SessionStart` hook (see `hooks/README.md`) so orientation happens without being remembered. The Hermes twin ships in `integrations/hermes/baseline-orient/` — a plugin whose `on_session_start` hook + `/orient` command run the same survey; this directive remains the tool-agnostic fallback (C28).

## Claiming a lane — before work starts (M5a)

In a repo whose descriptor declares `lanes.namespace`, **never hand-create a lane branch**. Claim it:

```bash
node "$SKILL_DIR/baseline.mjs" lane claim <issue> --repo <target>
```

- The claim is **atomic branch creation at origin** — the ref name is the namespace with the issue number substituted (`lane/22`), so two agents claiming the same issue race on one refname and exactly one wins. Exit 0 = yours (also when the lane already stands under your own agent trailer — reruns are idempotent); exit 3 = another agent holds it, cleanly (nothing was created locally): run `baseline orient` and pick different work. A hand-pushed branch (`git push origin HEAD:lane/22-foo`) mints a second, trailer-less lane for the issue — the exact dual-lane state the claim exists to prevent.

## Taking over a dead lane (M5b)

`orient`'s Lanes section derives every claimed lane's lease — **LIVE | STALE | ABANDONED | COMPLETED** (freshness = the later of tip commit and PR activity vs the descriptor's `lease_ttl`, default 7d; COMPLETED = the tip is already merged into the default branch — done, exempt from divergence/lease findings, prune it). Only a lane that **derives ABANDONED** is reclaimable:

```bash
node "$SKILL_DIR/baseline.mjs" lane reclaim <issue> --repo <target>
```

- The takeover is an empty child commit under your agent trailer, pushed under an exact-value CAS — a lane that moved mid-reclaim (someone pushed, rewound, or deleted it) rejects and the tool tells you the truth (exit 3: it's active). A dated takeover record is machine-written through `baseline log`, and the issue gets a best-effort comment. **Never bypass the gate with a plain `git push`** — a LIVE lane belongs to its agent; if a live takeover is genuinely sanctioned (agent on leave), record a `deviation` judgment naming the lane and pass `--jdg <id>`.

## Admitting a lane — before it merges (M6a)

A verdict is valid only for the state it evaluated: before merging a lane, re-derive at the merge point —

```bash
node "$SKILL_DIR/baseline.mjs" admit --repo <target>
```

- Exit 0 = admitted (advisory warns ride the output); **exit 1 = refused** — the branch is stale against the target (merge/rebase it, rerun), a blocker fired (a descriptor change without its same-PR judgment — DESC-03), or a fact admit genuinely gates on was unreadable; exit 2 = environment (no target, no descriptor at the target). The TARGET branch's descriptor governs the run — editing the descriptor on your own branch changes nothing until it merges, and doing so at all requires a same-PR judgment with subject exactly `baseline.repo.json`.

Every admit verdict carries a `provenance: inputs_digest …` receipt line (and JSON field) naming exactly what it was derived from — head/target shas, the target descriptor's blob OID, rules version, check runs, anchor state; unreachable planes read `not consulted`, never vanish. Paste it into the PR thread when the verdict matters.

For repos that adopt a generated index (`baseline gen index`, default `docs/INDEX.md`): the file's first line is a `baseline:generated` marker — **edit the records, not the file**; `baseline gen --check` in CI reds on drift with the exact regenerate command (zero marked views is trivially green, so un-adopted repos never see it). Repos that vendor the toolkit at `tools/baseline/` pin it with `baseline gen lock` (`tools/baseline.lock.json`, verified by REC-06) — re-pin in the same PR as every vendor bump.

On the DEFAULT branch (usually cron, not by hand), **`baseline reconcile`** is the morning-after twin — it re-derives main's standing and files findings as `baseline`-labeled, lifecycle-managed issues (dedup'd, closed when cleared, reopened on recurrence; a human close of an advisory filing is final). `--dry-run` prints the plan without writing. Exit 0 even with findings (the tracker is the alert surface — orient headlines them); exit 1 means delivery itself failed — even with zero findings (a dead cron must not stay green). A behind-or-dirty checkout of the default branch degrades to a labeled report-only run (exit 0, nothing filed); only a HEAD off the default branch's line refuses (exit 2) — it is not a lane command.

## Recording — the last act

When pausing or ending a working session in a repo that keeps records (a `records/` dir or a multi-lane descriptor), **write the session record before you stop** — one command, never an editor:

```bash
node "$SKILL_DIR/baseline.mjs" log --repo <target> -m "what happened and why; dead ends" --next "the one most useful next step"
```

- Lane, agent, and timestamp are derived (lane = current branch); the record lands at `records/sessions/<lane>/<date>-<time>-<agent>.md`, schema-validated, in the exact `next:` shape `orient` reads back at the next session start. That symmetry — orient first, log last — is the whole loop.
- The write is **scrub-gated**: a deterministic secret signature blocks (non-lossy — the draft survives under `.baseline/cache/` and the exact rerun is printed); a false positive becomes a dated judgment: rerun with `--allow <finding-id> --allow-reason "..."`. Never bypass a block by hand-writing the file instead — rotate the secret or record the judgment.
- Records are **append-only once committed**: never edit a committed session record; write the next one.

**Judgments** (accepting a risk, deviating from a rule, satisfying a manual rule) are ledger records, not chat: `baseline jdg new --kind <sign-off|deviation|risk-acceptance|break-glass> --subject <rule-or-scope> --reason "..." --review-by <date>` — every judgment expires; add a `--tripwire "fact op value"` so the engine can detect when the accepted world changes. `baseline jdg check` evaluates the ledger (exit 1 on tripped/expired/invalid records). **Never fake a sign-off**: a real dated judgment by the user, or nothing. The plain-git forms live in `CONTRACT.md`.

**Claims** (M4c): if CLAIM-07 warns about a legacy `docs/CLAIMS.json`, run `baseline gen migrate-claims` — it explodes the monolith into per-claim `records/claims/CLM-*.json` (the V1 id survives as `slug`), refuses invalid claims loudly, and is idempotent. Review + commit the records, then delete the monolith. Hand-written records are pushed through the same scrub as `log` when the pre-push hook is installed (`cp "$SKILL_DIR/hooks/scrub-pre-push.sh" <repo>/.git/hooks/pre-push`); `baseline scrub <files>` runs the scan on demand.

## Modes

Figure out intent from the user's words; default to **score**.

### orient — session start · "where am I" · "what should I do next"
Run the survey (see **Orientation — the first act** above): `node "$SKILL_DIR/baseline.mjs" orient --repo <target>`. Read divergence → lanes → backlog → this lane's `next:`, then act. This is the first act in a lane repo, not a scored gate.

### score (default)
1. Pick the target repo: an explicit path, else the current working directory. Confirm it looks like a repo (a manifest or `.git`).
2. Run the runner:
   ```bash
   node "$SKILL_DIR/check.mjs" --repo <target>
   ```
   - `--no-exec` — skip executing the repo's bootstrap/test command (BUILD-05). Use for untrusted repos or when the command isn't configured; otherwise prefer running it (BUILD-05 is the crown check).
   - `--profile advanced` — opt into expert rules (SBOM, code-scanning, mutation testing, dependency-vuln-scan, coverage-floor). `service` turns on automatically for `project_type=service`.
   - `--json` — machine output instead of the scorecard.
   - **Completion criterion:** you have the readiness %, the blocker count, and each FAIL/notable WARN with its one-line detail.
3. Present it: lead with **blockers** (they fail CI), then warnings worth fixing, grouped by category. Don't dump all 90 rows — summarize and offer to fix or scaffold.

### init — "set up / adopt / scaffold baseline"
**Descriptor-first, always.** The repo's `baseline.repo.json` is written before anything else — it's the one file baseline requires (schema: `schema/repo.schema.json`), and every applicability/severity derivation reads it. Its `type` supersedes filesystem auto-detection.
1. **Write the descriptor.** Copy the closest posture preset (or the blank template) to `<repo>/baseline.repo.json`, then set `type`, `lifecycle`, `maturity`, `workflow`, `anchoring`:
   ```bash
   cp "$SKILL_DIR/config-presets/multi-lane-agents.repo.json" <repo>/baseline.repo.json   # V2 default: lanes on
   # or readiness-only.repo.json (just the score, V1-equivalent) · or templates/baseline.repo.json (blank)
   ```
   Multi-lane is the default — any solo dev gets lanes out of the box; use `readiness-only` for the score with no workflow contract.
2. **Tune the checks (optional).** Copy the closest `config-presets/*.json` to `<repo>/baseline.config.json` for paths/commands/thresholds, or start from `config.example.json`. Then scaffold only what's missing (never overwrite without asking):
   ```bash
   cp "$SKILL_DIR/config-presets/node-service.json" <repo>/baseline.config.json   # tuning: bootstrap_command, globs…
   mkdir -p <repo>/records/claims && cp "$SKILL_DIR/templates/claim.json" <repo>/records/claims/CLM-0001.json   # only if it makes external claims — one claim, one record
   ```
   Per-claim records (`records/claims/CLM-NNNN.json`) are the **only** claims home the checker reads; a legacy `docs/CLAIMS.json` monolith is flagged by CLAIM-07 — migrate it (`baseline gen migrate-claims`, steps in `MIGRATION.md`).
3. Edit `baseline.config.json` to reality: `bootstrap_command` (clean-checkout install+test for BUILD-05), `makes_external_claims` (false skips CLAIM-*). Opt-in `*_globs` keys stay empty until adopted.
4. Wire the `baseline` job into CI as a **required** check (rule BUILD-06) — snippet is in `REFERENCE.md`.
5. Run a first score — `DESC-01` confirms the descriptor is present, `DESC-02` that it schema-validates.
- **Completion criterion:** `baseline.repo.json` exists and validates (DESC-01 + DESC-02 PASS), `node check.mjs --repo <repo>` runs, and every scaffolded artifact is accounted for.

### fix — "get this to green"
1. Score first. For each blocker/warn to address, apply the rule's own `fix` field (read it from `rules.json`) as concrete edits — add the missing LICENSE, pin the action to a SHA, git-ignore + rotate the `.env` secret, add the negative test, etc.
2. For `manual` (sign-off) rules, **don't fake the check** — do the judgment with the user (blast-radius, prior-art pass, wedge/moat) and record it as a dated, expiring judgment: `baseline jdg new --kind sign-off --subject <RULE-ID> --reason "..." --review-by <date>`.
3. Re-score to confirm.
- **Completion criterion:** re-score shows the targeted rules resolved and no new blockers introduced.

### explain — "what does SEC-03 check", "why did CTX-05 fail"
Read the rule from `rules.json` (`title`, `rationale`, `fix`, `source`, `check`) and explain it plainly plus what the runner actually looked for. For unfamiliar jargon (SBOM, SLSA, provenance, sign-off ledger, …) point to `GLOSSARY.md`.

## Rule-set integrity — `--self-check`

The rule set validates itself:
```bash
node "$SKILL_DIR/check.mjs" --self-check
```
Exits 1 on any rule with a missing/typo'd `applies_to`, an unknown check-kind / profile / severity / category / `requires` key, a duplicate id, or an orphan type/profile — and prints a per-type **coverage matrix**. Use it if you edit the rule modules under `rules/` (or the `rules.json` manifest), or wire it into CI so a malformed rule set can't merge.

## How the runner decides (so you can read detail lines)

- **PASS / FAIL / WARN / SIGN-OFF / SKIP** per rule; only a `blocker` FAIL sets exit 1.
- **SKIP** = the rule didn't apply: `applies_to` excludes the repo's `project_type` (`n/a for <type>`), an off profile (`profile 'advanced' off`), an unadopted opt-in, or nothing to check. A skip never counts against readiness.
- **`applies_to`** (`"all"` or a subset of `node`/`python`/`service`/`library`/`docs`) scopes each rule to the repo types it fits — e.g. a `docs` repo skips build/test/service rules.
- **Profiles:** `core` always; `service` auto-on for `project_type=service`; `advanced` only with `--profile advanced`.
- **Claims are opt-in:** CLAIM-* run only if a claims register exists or `makes_external_claims:true` is set.
- **Descriptor:** a `baseline.repo.json` declares the repo's identity/posture; its `type` supersedes auto-detection, and `DESC-01` warns (and offers to scaffold) when it's absent; a present-but-invalid one is `DESC-02`'s blocker.
- Config auto-detects; `baseline.config.json` at the repo root overrides (keys documented in `config.example.json`). The runner is zero-dependency and crash-resilient: an unevaluable check degrades to SKIP, never crashing the run.

## Common Pitfalls

1. **Copying `check.mjs` away from the rule set (`rules.json` + `rules/`) + `src/`.** It loads them from its own directory — invoke by absolute path instead.
2. **Presenting a warn as a blocker (or vice-versa).** Severity is in the rule modules (`rules/*.json`) and the runner output — never upgrade/downgrade it.
3. **Faking a sign-off.** Manual rules exist because a script can't judge them; record a real dated judgment (`baseline jdg new --kind sign-off`), don't rubber-stamp.
4. **Skipping BUILD-05 by habit.** Omit `--no-exec` when the repo is trusted and `bootstrap_command` is set — a green crown check is the strongest single signal.
5. **Gaming a warn to hit 100%.** An honest advisory warn (e.g. a dependency-updater rule on a zero-dep repo) beats a presence-theater fix. 0 blockers = build-ready is the real bar.

## Verification Checklist

- [ ] Ran the runner by its **absolute** path with `--repo <target>`
- [ ] Reported **blockers first**, then warnings, grouped by category (not a 90-row dump)
- [ ] For `fix`: re-scored and confirmed no new blockers
- [ ] For `init`: picked a preset/config, scaffolded only what was missing, ran a first score
- [ ] Any sign-off is a real dated judgment, not a rubber stamp
- [ ] `--self-check` still passes if the rule set (`rules.json` / `rules/*.json`) was edited
- [ ] Session end in a record-keeping repo: `baseline log` written (scrubbed, with a real `next:`)
