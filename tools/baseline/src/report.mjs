// Scorecard rendering: human-readable per-category report or --json machine
// output. Both return the process exit code (1 if any blocker FAILed).
import path from 'node:path'
import { sanitizeTTY } from './util.mjs'

export const CATS = { build: 'Build & execution', quality: 'Code quality', test: 'Tests & invariants', security: 'Security & supply-chain', repro: 'Reproducibility', ops: 'Operability (service)', governance: 'Change governance', community: 'Community & onboarding', context: 'Context management', claims: 'Claims discipline', records: 'Records & ledger', flow: 'Lane workflow', merge: 'Merge admission', div: 'Divergence (cross-tier)', desc: 'Repo descriptor' }

export function makeColor(JSON_OUT) {
  return (c, s) => (process.stdout.isTTY && !JSON_OUT) ? `\x1b[${c}m${s}\x1b[0m` : s
}

// M7a: a blocker-severity row fails whether it tagged FAIL or DIVERGED — the
// verdict class is preserved in the output; the EXIT treats both as blocking.
// One predicate, every counting seam (both reports here, admit's leg (b)).
export const isBlocking = x => x.r.severity === 'blocker' && (x.tag === 'FAIL' || x.tag === 'DIVERGED')

export function reportJson({ results, REPO, cfg, ACTIVE, HEAD }) {
  const out = { repo: REPO, project_type: cfg.project_type, profiles: [...ACTIVE], head: HEAD, results: results.map(x => ({ id: x.r.id, category: x.r.category, severity: x.r.severity, profile: x.r.profile || 'core', tag: x.tag, detail: x.detail })) }
  const blockers = results.filter(isBlocking).length
  out.summary = { blockers, pass: results.filter(x => x.tag === 'PASS').length, warn: results.filter(x => x.tag === 'WARN').length, diverged: results.filter(x => x.tag === 'DIVERGED').length, signoff: results.filter(x => x.tag === 'SIGN-OFF').length, skip: results.filter(x => x.tag === 'SKIP').length, total: results.length }
  console.log(JSON.stringify(out, null, 2))
  return blockers ? 1 : 0
}

export function reportHuman({ results, REPO, cfg, ACTIVE, HEAD, version, color }) {
  const TAG = { PASS: color(32, 'PASS'), FAIL: color(31, 'FAIL'), WARN: color(33, 'WARN'), DIVERGED: color(31, 'DIVERGED'), SKIP: color(90, 'SKIP'), 'SIGN-OFF': color(35, 'SIGN-OFF') }
  // pad to the widest tag (DIVERGED/SIGN-OFF = 8) by VISIBLE width — color the tag, then
  // append spaces, so the id column aligns in both TTY (ANSI-wrapped) and pipe modes; the
  // old `padEnd(tag.length + …)` padded each tag to its own length, i.e. never
  const TAGW = 8
  const tagCell = t => TAG[t] + ' '.repeat(Math.max(1, TAGW - t.length + 1))
  // repo-authored strings (rule details carry descriptor fields; titles are rule text)
  // are stripped of terminal control bytes before printing — no cursor-move that
  // overwrites a printed FAIL with fake PASS (--json is unaffected; JSON escapes them)
  const S = sanitizeTTY
  console.log(`\n  project-baseline v${version}  ·  ${path.basename(REPO)}  ·  type=${cfg.project_type}  ·  profiles=[${[...ACTIVE].join(',')}]  ·  HEAD=${HEAD || 'n/a'}\n`)
  for (const cat of Object.keys(CATS)) {
    const rows = results.filter(x => x.r.category === cat); if (!rows.length) continue
    console.log('  ' + color(1, CATS[cat]))
    for (const x of rows) console.log(`    ${tagCell(x.tag)} ${x.r.id.padEnd(9)} ${S(x.r.title)}\n            ${color(90, '↳ ' + S(x.detail))}`)
    console.log('')
  }
  const n = t => results.filter(x => x.tag === t).length
  const blockers = results.filter(isBlocking).length
  const scored = results.filter(x => x.tag !== 'SKIP').length
  const div = n('DIVERGED')
  console.log('  ' + color(1, 'Summary') + `  ${color(32, n('PASS') + ' pass')} · ${color(31, n('FAIL') + ' fail')} · ${color(33, n('WARN') + ' warn')}${div ? ` · ${color(31, div + ' diverged')}` : ''} · ${color(35, n('SIGN-OFF') + ' sign-off')} · ${color(90, n('SKIP') + ' n/a')}`)
  console.log(`  Readiness: ${Math.round(100 * n('PASS') / Math.max(1, scored))}%  (${n('PASS')}/${scored} applicable)`)
  console.log(blockers ? color(31, `\n  ✗ ${blockers} blocker(s) — not build-ready.\n`) : color(32, `\n  ✓ no blockers.\n`))
  return blockers ? 1 : 0
}
