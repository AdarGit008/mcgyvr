// `baseline orient` — the derived-state survey a session runs first (C16). It gathers facts
// from tree + history + forge (src/facts/*), joins them over declared keys (src/join.mjs),
// derives the status view (src/derive/status.mjs), then renders it. An agent helper, never a
// gate: every unreachable plane degrades to a labelled note and orient still prints what it
// derived (FS9 — never hard-refuses; only --strict turns forge-unreachability into exit 1).
// Generalizes the ADR-0009 prototype tools/orient.mjs.
import path from 'node:path'
import { makeOpt, sanitizeTTY } from './util.mjs'
import { indexRepo } from './repo.mjs'
import { loadDescriptor } from './descriptor.mjs'
import { capabilityProbe } from './probe.mjs'
import { gatherFacts } from './facts/index.mjs'
import { join } from './join.mjs'
import { deriveStatus } from './derive/status.mjs'

const fmtAge = (ms) => {
  if (ms == null) return '?'
  if (ms < 3600000) return 'just now'
  if (ms < 86400000) return `${Math.floor(ms / 3600000)}h ago`
  return `${Math.floor(ms / 86400000)}d ago`
}

export async function runOrient(argv) {
  if (argv[0] === '--help' || argv[0] === '-h') { console.log('baseline orient — derived-state survey for session start\n  usage: baseline orient [--repo DIR] [--json] [--strict]'); return 0 }
  const opt = makeOpt(argv)
  if (opt('--repo', null) === true) { console.error('orient: --repo needs a value'); return 2 }
  const REPO = path.resolve(opt('--repo', process.cwd()))
  const JSON_OUT = !!opt('--json', false)
  const STRICT = !!opt('--strict', false)

  const repo = indexRepo(REPO)
  const descriptor = loadDescriptor(repo)
  const cap = capabilityProbe(repo)
  const facts = gatherFacts(repo, { descriptor, capability: cap })
  const status = deriveStatus(facts, join(facts), cap)
  const exit = (STRICT && !cap.forge.available) ? 1 : 0

  if (JSON_OUT) { console.log(JSON.stringify({ repo: REPO, ...status, exit }, null, 2)); return exit }

  // ---- human survey (renders the derived status) ----
  // ONE clock: ages render against the now the view was DERIVED at (BASELINE_LOG_NOW
  // rides in) — a second Date.now() here would let PR ages drift while lane ages stay
  // pinned, and no replayed golden could ever pin a line
  const ageOf = (iso) => iso ? fmtAge(Date.parse(status.now) - new Date(iso).getTime()) : ''
  const P = []
  const capLine = c => c.available
    ? `✓${c.branch ? ` (${c.branch})` : c.repo ? ` (${c.repo})` : ''}${c.shallow ? ' [shallow]' : ''}`
    : `✗ (${c.reason})`
  const branch = status.thisLane.branch
  P.push(`\n# Orientation — ${path.basename(REPO)}${branch ? `  ·  ${branch}` : ''}\n`)
  P.push(`Planes: TREE ${capLine(cap.tree)} · HISTORY ${capLine(cap.history)} · FORGE ${capLine(cap.forge)}`)
  const d = status.descriptor
  P.push(d.present
    ? `Descriptor: ${d.valid ? `${d.type} · ${d.workflow}` : `present but INVALID (${d.errors[0] || 'schema error'})`}`
    : `Descriptor: undeclared — advisory orientation only (declare it: copy a config-presets/*.repo.json posture preset to baseline.repo.json)`)
  if (status.nowFallback) P.push(`_⚠ ${status.nowFallback}_`)

  if (status.findings.length) {
    P.push(`\n## ⚠ Unresolved joins (integrity)`)
    for (const f of status.findings) P.push(`- ${f.detail}`)
  }
  if (status.divergence.length) {
    P.push(`\n## ⚠ Divergence (resolve first)`)
    status.divergence.forEach((x, i) => {
      // cross-ref: a divergence reconcile already filed carries its issue on the SAME
      // line (a second full entry below would train skimming — the pre-defect)
      const code = status.divergenceCodes?.[i]
      const filedIssue = code && (status.filed || []).find(f => f.title.includes(`] ${code}:`))
      P.push(`- ${x}${filedIssue ? `  → filed as #${filedIssue.number}` : ''}`)
    })
  }
  // reconcile's open filings, ONE line (M6b): the act-now section stays first; the
  // zero case renders nothing (no wallpaper). The label is the mute affordance.
  if ((status.filed || []).length) {
    const top = status.filed.slice(0, 3).map(f => `#${f.number} ${f.title}`).join(' · ')
    P.push(`\n⚠ ${status.filed.length} baseline-filed issue(s) open — ${top}${status.filed.length > 3 ? ` (+${status.filed.length - 3} more)` : ''}  \`gh issue list --label baseline\``)
  }

  // ---- lanes: the derived lease view (C31) when the descriptor declares a namespace;
  // ---- the plain open-PR survey otherwise (single-lane repos keep their old section) ----
  const meta = status.lanesMeta
  const laneRefSet = new Set((status.lanes || []).map(l => l.ref))
  const STATE_ICON = { LIVE: '●', STALE: '◐', ABANDONED: '✗', COMPLETED: '✔' }
  if (meta) {
    P.push(`\n## Lanes (\`${meta.namespace}\` · ttl ${meta.ttl})`)
    if (meta.truncated) P.push(`_⚠ lane list truncated — refs beyond the forge's first page (100) are not shown_`)
    if (!status.lanes.length) P.push(meta.source ? `_none claimed_` : `_underived: ${meta.reason}_`)
    else for (const l of status.lanes) {
      const head = `- ${STATE_ICON[l.state] ?? '?'} \`${l.ref}\`${l.issue != null ? ` → #${l.issue}` : ''} — ${l.state ?? 'UNDERIVED'} · ${fmtAge(l.age_ms)} · agent ${l.agent ?? '?'}`
      const pr = l.pr ? ` · PR #${l.pr.number}${l.pr.draft ? ' [draft]' : ''}` : ' · no PR yet'
      P.push(head + pr)
      for (const lab of l.labels) P.push(`    · ${lab}`)
      // the recipe must be runnable verbatim: reclaim refuses an anchor-less ref, so an
      // abandoned lane without an issue anchor gets the honest line, never a dead recipe
      if (l.state === 'ABANDONED') P.push(l.issue != null
        ? `    ↳ reclaimable:  baseline lane reclaim ${l.issue}`
        : `    ↳ not machine-reclaimable (no issue anchor) — rename or delete the branch by hand`)
      if (l.pr) P.push(l.next ? `    ↳ next: ${l.next}` : l.hasLog ? `    ↳ (session log has no filled-in next:)` : l.hasLog === false ? `    ↳ (no session log on branch)` : `    ↳ (session log not fetched for this lane)`)
    }
  }

  // the probe's reason is the specific one ("gh not installed", "no forge repo resolves
  // here") — makeForge's generic 'forge unreachable' must not shadow it into "forge
  // unreachable (forge unreachable)"
  const forgeWhy = status.forgeReason === 'forge unreachable' ? (cap.forge.reason || status.forgeReason) : (status.forgeReason || cap.forge.reason)
  const prHead = meta ? `\n## Open PRs${laneRefSet.size ? ' (non-lane branches)' : ''}` : `\n## Live lanes (open PRs)`
  const prList = (status.prs || []).filter(pr => !laneRefSet.has(pr.branch))
  P.push(prHead)
  if (!status.forgeAvailable) P.push(status.source === 'posture' ? `_${status.forgeReason}_` : `_forge unreachable (${forgeWhy}) — by hand: \`gh pr list\`_`)
  else if (!prList.length) P.push(`_none_`)
  else for (const l of prList) {
    P.push(`- #${l.number}${l.draft ? ' [draft]' : ''} ${l.title}  \`${l.branch}\`  (${ageOf(l.updatedAt)})${l.closes?.length ? `  → closes #${l.closes.join(', #')}` : ''}`)
    P.push(l.next ? `    ↳ next: ${l.next}` : l.hasLog ? `    ↳ (session log has no filled-in next:)` : `    ↳ (no session log on branch)`)
  }

  P.push(`\n## Backlog (open issues)`)
  if (!status.forgeAvailable) P.push(status.source === 'posture' ? `_${status.forgeReason}_` : `_forge unreachable — by hand: \`gh issue list\`_`)
  else if (!status.backlog.length) P.push(`_none_`)
  else {
    const byMs = new Map()
    for (const it of status.backlog) { const k = it.milestone ?? '(no milestone)'; (byMs.get(k) || byMs.set(k, []).get(k)).push(it) }
    for (const [ms, list] of [...byMs.entries()].sort()) {
      P.push(`\n### ${ms}`)
      for (const it of list.sort((a, b) => a.number - b.number)) P.push(`- #${it.number} ${it.title}${it.labels.length ? `  _[${it.labels.join(', ')}]_` : ''}`)
    }
  }

  P.push(`\n## This lane (${branch || 'no git'})`)
  if (!branch) P.push(`_${cap.history.reason || 'no branch'}_`)
  else P.push(status.thisLane.next ? `    ↳ next: ${status.thisLane.next}  (${status.thisLane.rel})` : status.thisLane.rel ? `    ↳ (${status.thisLane.rel} has no filled-in next:)` : `    ↳ (no session log yet on this branch)`)
  P.push('')

  // orient prints plain markdown (no color/escapes of its own), so the ONLY control
  // bytes in the output would be injected via repo-authored strings — issue/PR titles,
  // record next:, agent trailers, lane labels. Strip them at the render boundary (tab +
  // newline preserved); the --json branch above is untouched (JSON escapes control bytes).
  console.log(sanitizeTTY(P.join('\n')))
  return exit
}
