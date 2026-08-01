// The C39 repo descriptor: baseline.repo.json — the repo's declared identity and
// posture. This is the one stored piece of intent every applicability, severity, and
// join derivation hangs off; keeping it small and schema-bound is what stops it from
// regrowing into a status blob. Read from the working tree, or from a git ref (the
// target-ref anchor seam, FS1 — enforcing contexts pass the default branch so a PR
// cannot weaken the posture that judges it). Validated by a zero-dependency subset
// validator against schema/repo.schema.json (the single source of truth).
import fs from 'node:fs'
import { execFileSync } from 'node:child_process'
import { validateAgainst } from './validate.mjs'

export const DESCRIPTOR_FILE = 'baseline.repo.json'

// The schema is the single source of truth for both validation here and the docs.
export const DESCRIPTOR_SCHEMA = JSON.parse(fs.readFileSync(new URL('../schema/repo.schema.json', import.meta.url), 'utf8'))

// Which module consumes each descriptor field. --self-check (S7 / DESC-02) asserts every
// schema property appears here and vice-versa, so no field is silently unconsumed and
// every deferral is auditable. 'M2' = wired and active now; 'reserved:Mx' = declared now,
// switched on when module Mx lands (the honest-slice ruling — nothing pretends to work).
export const FIELD_CONSUMERS = {
  schema_version:        'M2 · loader compatibility gate',
  type:                  'M2 · config.project_type — supersedes filesystem auto-detection',
  lifecycle:             'reserved:M7 · record-scrutiny promotion (M4 shipped no lifecycle consumer; #24 decides consume-or-drop)',
  maturity:              'M4c · config CLAIMS_ACTIVE gate — CLAIM category activates at "claimed" (C24, discrete tiers)',
  workflow:              'M4c · engine posture gate — rules declaring `workflow` SKIP on other postures; string-or-array families since M5c',
  anchoring:             'M5c · FLOW-01 anchoring knob — off SKIPs, relaxed wants a parseable anchor, strict also wants forge resolution',
  ground_truth_boundary: 'M4c · engine default-branch lane gate (branch_scope rules); probe/target-ref reads reserved:M6',
  lanes:                 'M5a/M5b/M5c · claim branch namespace (M5a); lease_ttl in the lease derivation (M5b); families in FLOW-04 placement (M5c)',
  join_keys:             'M5a · lane claim trailer allowlist (C38 — claim machine-generates only declared keys)',
  engine_pin:            'reserved:M7 · pointer-install skew detection',
  staleness:             'reserved:M3 · orient staleness ceilings',
}

// The subset validator lives in src/validate.mjs since M4a (shared with the record
// schemas); the descriptor's messages and semantics are unchanged.

function readSource(repo, ref) {
  if (ref) {
    // filenames/ref are literal argv (execFileSync, no shell) — never a shell string
    try { return execFileSync('git', ['show', `${ref}:${DESCRIPTOR_FILE}`], { cwd: repo.REPO, stdio: ['ignore', 'pipe', 'ignore'] }).toString('utf8') } catch { return null }
  }
  return repo.read(DESCRIPTOR_FILE)
}

// -> { present, valid, data, errors, source }. `data` is the parsed object even when
// invalid (for diagnostics); consumers gate on `valid` before trusting a field.
export function loadDescriptor(repo, { ref = null } = {}) {
  const source = ref ? `ref:${ref}` : 'worktree'
  const raw = readSource(repo, ref)
  if (raw == null) return { present: false, valid: false, data: null, errors: [], source }
  let data
  try { data = JSON.parse(raw) } catch { return { present: true, valid: false, data: null, errors: ['not valid JSON'], source } }
  // Schema evolution vs the target-ref seam (M7b): a committed descriptor that was
  // valid under its era's schema may carry a field a later engine dropped (e.g.
  // `owner`). A ref-read serves POSTURE FACTS about an already-admitted state, so
  // an unknown field there is ignored, not fatal — otherwise every schema
  // contraction bricks admit against the very target the contracting PR must land
  // on (the M6 relief-circularity class). The WORKTREE read stays strict: the
  // state being authored next validates against today's schema, and DESC-02
  // (blocker since the M7c split) carries the pressure to shed retired fields.
  if (ref && data && typeof data === 'object' && !Array.isArray(data)) {
    const known = new Set(Object.keys(DESCRIPTOR_SCHEMA.properties || {}))
    for (const k of Object.keys(data)) if (!known.has(k) && !k.startsWith('_')) delete data[k]
  }
  const errors = []
  validateAgainst(data, DESCRIPTOR_SCHEMA, '', errors)
  return { present: true, valid: errors.length === 0, data, errors, source }
}
