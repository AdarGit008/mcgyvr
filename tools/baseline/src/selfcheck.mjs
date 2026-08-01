// --self-check: validate rules.json integrity (no dangling scopes/kinds/types)
// and print the per-type coverage matrix. Returns the process exit code.
import { CATS } from './report.mjs'
import { DESCRIPTOR_SCHEMA, FIELD_CONSUMERS } from './descriptor.mjs'

export function runSelfCheck({ RULES, TYPES, CHECK_KINDS, DEFAULTS, color }) {
  const problems = []
  const typeSet = new Set(TYPES)
  const profileKeys = new Set(Object.keys(RULES.profiles || {}))
  const sevOk = new Set(['blocker', 'warn', 'manual'])
  const catKeys = new Set(Object.keys(CATS))
  const ids = new Set()
  const expand = r => r.applies_to === 'all' ? TYPES : (Array.isArray(r.applies_to) ? r.applies_to : [])
  let curId
  const checkKinds = c => {
    if (!c || typeof c !== 'object') return
    if (c.kind) { if (!CHECK_KINDS.has(c.kind)) problems.push(`${curId}: unknown check kind '${c.kind}'`) }
    for (const sub of (c.checks || [])) checkKinds(sub)
    if (c.when) checkKinds(c.when)
    if (c.then) checkKinds(c.then)
  }
  for (const r of RULES.rules) {
    curId = r.id || '(rule with no id)'
    if (!r.id) problems.push('a rule is missing "id"')
    else if (ids.has(r.id)) problems.push(`duplicate rule id: ${r.id}`)
    else ids.add(r.id)
    if (r.applies_to === undefined) problems.push(`${curId}: missing applies_to (must be "all" or a subset of project_types)`)
    else if (r.applies_to !== 'all') {
      if (!Array.isArray(r.applies_to) || r.applies_to.length === 0) problems.push(`${curId}: applies_to must be "all" or a non-empty array`)
      else for (const t of r.applies_to) if (!typeSet.has(t)) problems.push(`${curId}: applies_to has unknown type '${t}' (not in project_types)`)
    }
    if (r.profile !== undefined && !profileKeys.has(r.profile)) problems.push(`${curId}: unknown profile '${r.profile}'`)
    if (!sevOk.has(r.severity)) problems.push(`${curId}: invalid severity '${r.severity}'`)
    if (!catKeys.has(r.category)) problems.push(`${curId}: unknown category '${r.category}'`)
    if (r.requires !== undefined && !(r.requires in DEFAULTS)) problems.push(`${curId}: 'requires' names unknown config key '${r.requires}'`)
    // M4c posture/branch gates are data: a rule may declare the workflow(s) it needs
    // and/or that it only runs on a lane (non-default) branch — values are closed sets,
    // and branch_scope REQUIRES workflow: a lane rule without a posture gate would run
    // on every non-default branch of every undeclared repo (the wallpaper-warn class the
    // M4 ruling forbids) — "no wallpaper warns is structural" is a law, not a habit.
    // String-or-array since M5c (a rule may serve a posture FAMILY); the value set is
    // read from the descriptor schema itself — lockstep by construction, not by habit.
    if (r.workflow !== undefined) {
      const wfEnum = DESCRIPTOR_SCHEMA.properties?.workflow?.enum || []
      const wfs = Array.isArray(r.workflow) ? r.workflow : [r.workflow]
      if (!wfs.length) problems.push(`${curId}: workflow must be a value or non-empty array from the descriptor schema enum`)
      for (const w of wfs) if (!wfEnum.includes(w)) problems.push(`${curId}: workflow '${w}' is not in the descriptor schema enum {${wfEnum.join('|')}}`)
    }
    if (r.branch_scope !== undefined && r.branch_scope !== 'lane') problems.push(`${curId}: branch_scope must be 'lane' (got '${r.branch_scope}')`)
    if (r.branch_scope !== undefined && r.workflow === undefined) problems.push(`${curId}: branch_scope requires a workflow declaration — a lane rule must be posture-gated (no wallpaper warns)`)
    // M4c review ruling: the CLAIM family is uniformly opt-in — a claims rule
    // without the family gate would fire on repos that never opted into claims
    // discipline (the CLAIM-06 wallpaper class, fixed once, kept fixed here).
    if (r.category === 'claims' && r.requires !== 'makes_external_claims') problems.push(`${curId}: claims-category rules must carry requires:makes_external_claims (uniform family opt-in)`)
    checkKinds(r.check)
  }
  for (const t of TYPES) if (!RULES.rules.some(r => expand(r).includes(t))) problems.push(`no rule applies to type '${t}' (orphan type)`)
  for (const p of profileKeys) {
    const has = p === 'core' ? RULES.rules.some(r => !r.profile) : RULES.rules.some(r => r.profile === p)
    if (!has) problems.push(`no rule uses profile '${p}' (orphan profile)`)
  }

  // S7 (DESC-02): the descriptor schema and the engine's consumption map stay in lockstep —
  // every declared field has a consumer (active now, or reserved for a NAMED later module), and
  // no consumer names a field the schema lacks. This is DESC-02 rehomed to the skill's own
  // self-check: it's an engine property, not a repo property. It makes every honest-slice
  // deferral auditable — a field can't be silently added and left unconsumed, nor claimed as
  // consumed without existing in the schema.
  const descProps = Object.keys(DESCRIPTOR_SCHEMA.properties || {})
  for (const f of descProps) if (!(f in FIELD_CONSUMERS)) problems.push(`descriptor field '${f}' has no declared consumer (add it to FIELD_CONSUMERS in src/descriptor.mjs)`)
  for (const f of Object.keys(FIELD_CONSUMERS)) if (!descProps.includes(f)) problems.push(`FIELD_CONSUMERS names '${f}', which is absent from the descriptor schema`)
  // M6a: x-strictness (DESC-03's weakening ladder) is schema DATA — each order must be a
  // total order over exactly its enum, or the classifier and the validator drift apart.
  for (const [f, p] of Object.entries(DESCRIPTOR_SCHEMA.properties || {})) {
    if (!p['x-strictness']) continue
    const order = [...p['x-strictness']].sort().join('|'), en = [...(p.enum || [])].sort().join('|')
    if (order !== en) problems.push(`schema property '${f}': x-strictness must be a total order over exactly the enum values (order {${p['x-strictness'].join(',')}} vs enum {${(p.enum || []).join(',')}})`)
  }

  // M3c: rule-metadata invariants. Every rule declares which planes it reads (sources), what it does
  // when a source is unreachable (on_unreachable), the contexts it runs in, and its certainty — and
  // two structural laws hold (the STRATA graft): a blocker must be deterministic, a sign-off must be
  // judgment. Plus layering: a readiness rule may not consume FLOW facts (inert until M5 adds 'flow').
  const SRC = new Set(['tree', 'history', 'forge', 'exec'])
  const CTXV = new Set(['check', 'admit', 'reconcile'])
  const UNR = new Set(['skip', 'fail', 'stale-ok'])
  const CERT = new Set(['deterministic', 'heuristic', 'judgment'])
  for (const r of RULES.rules) {
    const id = r.id || '(no id)'
    if (!Array.isArray(r.sources) || !r.sources.length || !r.sources.every(s => SRC.has(s))) problems.push(`${id}: sources must be a non-empty subset of {${[...SRC].join('|')}}`)
    if (!UNR.has(r.on_unreachable)) problems.push(`${id}: on_unreachable must be one of {${[...UNR].join('|')}}`)
    if (!Array.isArray(r.contexts) || !r.contexts.length || !r.contexts.every(c => CTXV.has(c))) problems.push(`${id}: contexts must be a non-empty subset of {${[...CTXV].join('|')}}`)
    if (!CERT.has(r.certainty)) problems.push(`${id}: certainty must be one of {${[...CERT].join('|')}}`)
    if (r.severity === 'blocker' && r.certainty !== 'deterministic') problems.push(`${id}: blocker must be deterministic (got '${r.certainty}') — a blocker can't rest on a heuristic/judgment`)
    // M7a: the div⇒warn (M5c) and merge⇒warn (M6a) laws LIFTED with the promotion —
    // the counting seams (report.isBlocking, shared by check's exits and admit's
    // leg (b)) now treat blocker-severity DIVERGED as failing, so the dead path
    // those laws pinned shut no longer exists. The general blocker⇒deterministic
    // law above covers the promoted set.
    // M6b: reconcile runs ON the default branch — a lane-scoped rule there is
    // unrepresentable (the branch gate would SKIP it on every single run, the exact
    // wallpaper class the context gate exists to kill). Exclusion is structural:
    // declaring both is an integrity error, not a permanent SKIP row.
    if (r.branch_scope === 'lane' && Array.isArray(r.contexts) && r.contexts.includes('reconcile')) problems.push(`${id}: branch_scope 'lane' cannot declare context 'reconcile' — reconcile runs on the default branch, where lane rules are unrepresentable (exclusion, not a wallpaper SKIP)`)
    if (r.severity === 'manual' && r.certainty !== 'judgment') problems.push(`${id}: sign-off (manual) must be certainty 'judgment' (got '${r.certainty}')`)
    if (r.certainty === 'judgment' && r.severity !== 'manual') problems.push(`${id}: certainty 'judgment' must route to a sign-off (severity 'manual', got '${r.severity}')`)
    if (Array.isArray(r.sources) && r.sources.includes('flow')) problems.push(`${id}: readiness rules may not consume 'flow' facts (layering invariant)`)
  }
  // coverage matrix: applicable rules per type, split by profile
  const profOf = r => r.profile || 'core'
  console.log(`\n  project-baseline self-check · v${RULES.version} · ${RULES.rules.length} rules · types=[${TYPES.join(', ')}]\n`)
  console.log('  Coverage — rules applicable per project type:')
  console.log('    type        core  service  advanced   total')
  for (const t of TYPES) {
    const appl = RULES.rules.filter(r => expand(r).includes(t))
    const by = { core: 0, service: 0, advanced: 0 }
    for (const r of appl) by[profOf(r)] = (by[profOf(r)] || 0) + 1
    console.log(`    ${t.padEnd(10)}  ${String(by.core).padStart(4)}  ${String(by.service).padStart(7)}  ${String(by.advanced).padStart(8)}  ${String(appl.length).padStart(6)}`)
  }
  console.log('')
  const activeN = descProps.filter(f => /^M\d/.test(FIELD_CONSUMERS[f] || '')).length
  console.log(`  Descriptor — ${descProps.length} schema field(s): ${activeN} active, ${descProps.length - activeN} reserved for later modules; every field has a declared consumer (S7).\n`)
  const cBy = c => RULES.rules.filter(r => r.certainty === c).length
  console.log(`  Metadata — every rule declares sources/on_unreachable/contexts/certainty; certainty: ${cBy('deterministic')} deterministic, ${cBy('heuristic')} heuristic, ${cBy('judgment')} judgment. Laws: blocker⇒deterministic, sign-off⇒judgment.\n`)
  if (problems.length) {
    console.log(color(31, `  ✗ ${problems.length} integrity problem(s):`))
    for (const p of problems.slice(0, 60)) console.log('    - ' + p)
    console.log('')
    return 1
  }
  console.log(color(32, `  ✓ rule set is internally consistent — every rule carries a valid applies_to, profile, kind, severity, and category; all ${TYPES.length} types and ${profileKeys.size} profiles are covered.\n`))
  return 0
}
