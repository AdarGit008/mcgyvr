// DESC-03's posture-diff classifier (M6a) — pure, deterministic, schema-driven.
// "Weakening is schema data, not judgment": the posture enums declare their ascending
// x-strictness order in schema/repo.schema.json (selfcheck holds order == enum), and
// the gate-consumed structural fields below carry set-rules. Everything else is a
// tuning knob — posture-neutral by ruling (lease_ttl, staleness, families, engine_pin,
// owner, lifecycle). The classification rides DESC-03's finding text now and is M7's
// per-axis promotion seam; the M6 verdict itself keys only on "descriptor changed
// without its same-range judgment", so a conservative entry here costs one honest
// JDG ceremony, never a wall.
import { getPath } from '../util.mjs'

// Gate-consumed structural fields (each names its consumer): ANY change is a weakening —
// changing them silently re-aims what the gates compare against.
const STRUCTURAL = [
  ['type', 'rule applicability (applies_to)'],
  ['lanes.namespace', 'the claim primitive + FLOW-04 placement'],
  ['ground_truth_boundary.default_branch', 'the target-ref policy (FS1) + lane gates'],
]

// -> [strings], each one classified weakening; empty = nothing weakening (additive/
// tuning/neutral). `before` is the TARGET ref's descriptor data (valid by the caller's
// gate); `after` is the head's parsed data, or null when unparseable/schema-invalid —
// invalidation turns the whole posture off, the ultimate weakening.
export function classifyPostureDiff(before, after, schema) {
  if (!before || typeof before !== 'object') return []
  if (!after || typeof after !== 'object') return ['descriptor invalidated — the declared posture turns off entirely']
  const found = []
  // enum down-ladder per x-strictness (ascending order; a move to a lower index weakens)
  for (const [field, prop] of Object.entries(schema?.properties || {})) {
    const order = prop['x-strictness']
    if (!Array.isArray(order)) continue
    const from = before[field], to = after[field]
    if (from === to || from === undefined) continue
    const fi = order.indexOf(from), ti = order.indexOf(to)
    if (fi < 0) continue // before-value outside the order: schema drift, not classifiable here
    if (to === undefined) { found.push(`${field} removed (was '${from}')`); continue }
    if (ti >= 0 && ti < fi) found.push(`${field}: '${from}' → '${to}' (down-ladder)`)
  }
  // structural set-rules: any change (incl. removal) to a gate-consumed field
  for (const [pathKey, consumer] of STRUCTURAL) {
    const from = getPath(before, pathKey), to = getPath(after, pathKey)
    if (from === undefined || String(from) === String(to)) continue
    found.push(`${pathKey}: ${JSON.stringify(from)} → ${to === undefined ? 'removed' : JSON.stringify(to)} (consumed by ${consumer})`)
  }
  // join_keys shrink: removing a declared join key orphans the trailers already minted
  const jkFrom = Array.isArray(before.join_keys) ? before.join_keys : []
  const jkTo = new Set(Array.isArray(after.join_keys) ? after.join_keys : [])
  const dropped = jkFrom.filter(k => !jkTo.has(k))
  if (dropped.length) found.push(`join_keys shrank (dropped ${dropped.join(', ')}) — existing trailers orphaned`)
  return found
}
