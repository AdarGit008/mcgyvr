// The gate -> evaluate -> tag pipeline. Gates can short-circuit a rule to SKIP
// (wrong type, off profile, opted out, wrong posture, wrong branch) before its
// check ever runs; only a blocker that evaluates to false FAILs. An erroring
// check degrades to SKIP. The posture/branch gates are data-driven (a rule
// declares `workflow` / `branch_scope`), so "no wallpaper warns" is structural:
// a lane rule is unrepresentable as a finding on a single-lane repo or on the
// default branch — it never runs there.
export function runRules({ rules, cfg, ACTIVE, CLAIMS_ACTIVE, evalCheck, DESCRIPTOR = null, BRANCH = null, DEFAULT_BRANCH = null, CLAIMS_REASON = null, context = 'check' }) {
  const results = []
  for (const r of rules) {
    // M6a: context-gated execution — the first real consumer of rule `contexts`. A rule
    // outside the run's context is EXCLUDED (no row), never a SKIP: a "wrong context" row
    // on every check run would be the exact wallpaper class the other gates exist to kill.
    // Every pre-M6 rule declares 'check' (selfcheck enforces non-empty contexts), so
    // check-context output is byte-identical at rest — the gate re-pins nothing.
    if (!Array.isArray(r.contexts) || !r.contexts.includes(context)) continue
    if (r.applies_to && r.applies_to !== 'all' && !r.applies_to.includes(cfg.project_type)) { results.push({ r, tag: 'SKIP', detail: `n/a for ${cfg.project_type}` }); continue }
    if (r.profile && !ACTIVE.has(r.profile)) { results.push({ r, tag: 'SKIP', detail: `profile '${r.profile}' off` }); continue }
    // `requires` gates a rule on a config key. Its one non-claims consumer (CTX's
    // status_file, with the descriptor-honored `:false` carve-out) retired with the
    // stored-status surface at M7b — a future requires key adds its opt-out
    // semantics consciously, here, not by inheriting a dead branch.
    if (r.requires === 'makes_external_claims') { if (!CLAIMS_ACTIVE) { results.push({ r, tag: 'SKIP', detail: CLAIMS_REASON || 'claims opt-in (no register; set makes_external_claims:true to enable)' }); continue } }
    if (r.workflow) {
      if (!DESCRIPTOR || !DESCRIPTOR.valid) { results.push({ r, tag: 'SKIP', detail: 'workflow contract off (no valid baseline.repo.json)' }); continue }
      // string-or-array (M5c): a rule may serve a posture FAMILY — e.g. the lane rules
      // run under multi-lane AND multi-lane-local, whose difference is forge access,
      // not lane discipline; forge-dependent checks still degrade inside the evaluator
      const wfs = Array.isArray(r.workflow) ? r.workflow : [r.workflow]
      if (!wfs.includes(DESCRIPTOR.data.workflow)) { results.push({ r, tag: 'SKIP', detail: `workflow=${DESCRIPTOR.data.workflow} (rule needs ${wfs.join('|')})` }); continue }
    }
    if (r.branch_scope === 'lane') {
      if (!BRANCH) { results.push({ r, tag: 'SKIP', detail: 'no branch resolved (detached HEAD / CI checkout) — lane rules n/a' }); continue }
      // an undeclared default branch is a SKIP, never a guessed 'main' — a guess can
      // put lane rules ON the real default branch, the exact wallpaper the gate forbids
      if (!DEFAULT_BRANCH) { results.push({ r, tag: 'SKIP', detail: 'default branch undeclared (set ground_truth_boundary.default_branch) — lane rules n/a' }); continue }
      if (BRANCH === DEFAULT_BRANCH) { results.push({ r, tag: 'SKIP', detail: `on default branch '${DEFAULT_BRANCH}' — lane rules n/a` }); continue }
    }
    let res; try { res = evalCheck(r.check, r) } catch (e) { res = { ok: null, detail: 'check errored: ' + String(e.message).slice(0, 60) } }
    let tag
    if (res.ok === null) tag = 'SKIP'
    else if (res.ok === true) tag = 'PASS'
    // M5c: a cross-tier contradiction is its own verdict, not a generic warn — the
    // DIVERGED tag survives promotion (M7a): a blocker-severity DIVERGED row keeps
    // this tag and the COUNTING seams (report exits, admit leg (b)) treat it as
    // failing. The verdict class is never erased into a generic FAIL.
    else if (res.diverged) tag = 'DIVERGED'
    else if (res.signoff || r.check.kind === 'signoff') tag = 'SIGN-OFF'
    // res.soft downgrades to WARN. The law, stated precisely (M7c panel corrected
    // the absolute form): soft-on-a-blocker is a DELIBERATE adoption-path downgrade
    // that exists in exactly one place today — BUILD-05 (kind `command`) with no
    // bootstrap_command configured softens to WARN (unconfigured ≠ failing). Every
    // other soft consumer rides warn-severity rules (records-scrub heuristics,
    // descriptor absence), where soft is a no-op. NO NEW blocker kind may lean on
    // soft — a soft return slips past isBlocking, so each one is a hole in the
    // gate that must be argued as an adoption path, on the record, like BUILD-05.
    else if (res.soft) tag = 'WARN'
    else tag = r.severity === 'blocker' ? 'FAIL' : 'WARN'
    results.push({ r, tag, detail: res.detail })
  }
  return results
}
