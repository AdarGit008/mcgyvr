// The judgment ledger surface (M4b) — records/judgments/JDG-NNNN.json, one owned
// file per judgment (C17). Two commands over one pure core:
//
//   baseline jdg new    author a judgment (schema-valid, scrub-gated, numbered)
//   baseline jdg check  evaluate every judgment's machine contract against facts
//
// The machine contract (C08): expected_state is the world the judgment assumed
// (drift = re-look), tripwire is the condition that VOIDS it (fired = act),
// review_by is the expiry (every judgment lapses — ledgers must not fossilize).
// evaluateJudgment is pure and returns STRUCTURED findings ({code, fact, want,
// got, text}) so M6's reconcile can dedup-key firings without parsing prose; the
// CLI renders text at the edge. One clock: facts.today governs everything —
// a --facts overlay time-travels the whole contract consistently. An
// unresolvable fact path is a FINDING, never a guess (C36). Verdict lattice,
// worst wins: tripped > expired > unresolvable > drifted > ok.
// Exit (check): 0 healthy · 1 any tripped/expired/invalid record. (new): 0
// written · 1 scrub-blocked · 2 usage. BASELINE_LOG_NOW (via util.nowUTC) is the
// clock override shared by all record tooling.
import fs from 'node:fs'
import path from 'node:path'
import { makeOpt, makeOptText, makeOptAll, getPath, nowUTC, deepEq } from './util.mjs'
import { run, capabilityProbe, currentLane } from './probe.mjs'
import { liteRepo } from './repo.mjs'
import { loadDescriptor } from './descriptor.mjs'
import { validateRecord } from './records.mjs'
import { scan, loadAllowlist, addAllowlistEntries, keepDraft } from './scrub.mjs'

export const JUDGMENTS_DIR = 'records/judgments'
// One parse-fan-out ceiling for every ledger consumer (M7c one-homed it): admit's
// added-judgment parse, reconcile's sweep, reconcile's landed-record re-scan. A
// range or tip carrying thousands of record files must not buy thousands of git
// spawns; every capped surface LABELS the truncation — bounded work, never
// silently-complete work.
export const JDG_PARSE_CAP = 500
const KINDS = ['sign-off', 'deviation', 'risk-acceptance', 'break-glass']
const ORDER = { ok: 0, drifted: 1, unresolvable: 2, expired: 3, tripped: 4 }

// -> { records, findings } — findings are ledger-integrity problems (unparseable
// file, schema-invalid record, id/filename mismatch), each { file, error }.
export function loadJudgments(REPO) {
  const dir = path.join(REPO, JUDGMENTS_DIR)
  let names = []
  try { names = fs.readdirSync(dir).filter(f => f.endsWith('.json')).sort() } catch { return { records: [], findings: [] } }
  const records = [], findings = []
  for (const f of names) {
    let data
    try { data = JSON.parse(fs.readFileSync(path.join(dir, f), 'utf8')) }
    catch { findings.push({ file: `${JUDGMENTS_DIR}/${f}`, error: 'not valid JSON' }); continue }
    const errors = validateRecord('judgment', data)
    if (errors.length) { findings.push({ file: `${JUDGMENTS_DIR}/${f}`, error: errors.slice(0, 3).join('; ') }); continue }
    if (data.id !== f.replace(/\.json$/, '')) { findings.push({ file: `${JUDGMENTS_DIR}/${f}`, error: `id '${data.id}' does not match filename` }); continue }
    records.push(data)
  }
  return { records, findings }
}

// The judgments ledger AT A GIT REF (M6a) — same validation loop as loadJudgments,
// reading committed blobs instead of the worktree. FS5's consumer: admit honors a
// break-glass only from the TARGET ref (main) — a judgment riding the incoming branch
// must never relieve the gate that judges that branch. reachable:false = the ref
// itself did not resolve (callers surface that, never fold it into "no judgments");
// a resolvable ref with no records/judgments/ is an honestly empty ledger.
export function loadJudgmentsAt(REPO, ref) {
  const out = run('git', ['-C', REPO, 'ls-tree', '--name-only', ref, JUDGMENTS_DIR + '/'])
  if (out === null) return { records: [], findings: [], reachable: false }
  const names = out.split('\n').map(s => s.trim()).filter(f => f.endsWith('.json')).sort()
  const records = [], findings = []
  for (const rel of names) {
    const f = rel.split('/').pop()
    const raw = run('git', ['-C', REPO, 'show', `${ref}:${rel}`])
    let data
    try { data = JSON.parse(raw) } catch { findings.push({ file: rel, error: 'not valid JSON' }); continue }
    const errors = validateRecord('judgment', data)
    if (errors.length) { findings.push({ file: rel, error: errors.slice(0, 3).join('; ') }); continue }
    if (data.id !== f.replace(/\.json$/, '')) { findings.push({ file: rel, error: `id '${data.id}' does not match filename` }); continue }
    records.push(data)
  }
  return { records, findings, reachable: true }
}

// Break-glass selection, one home (M6b extraction of admit's inline filter): the
// newest unexpired break-glass for a gate — date desc, id desc on ties. admit
// consults gate:'admit' from the TARGET ledger (FS5); reconcile consults
// gate:'reconcile' for delivery relief. One filter, or the two gates drift.
export function selectBreakGlass(records, gate, today) {
  return records
    .filter(j => j.kind === 'break-glass' && j.gate === gate && j.review_by >= today)
    .sort((a, b) => (a.date === b.date ? (a.id < b.id ? 1 : -1) : (a.date < b.date ? 1 : -1)))[0] || null
}

// The bridge's selection rule, one home: schema-VALID sign-offs only (a malformed
// review_by must never read as signed-forever), newest per subject — date desc,
// id desc on ties. The newest governs even if lapsed: a re-judgment supersedes;
// an older unexpired record does not resurrect (documented in CONTRACT.md).
export function selectSignoffs(records) {
  const by = {}
  for (const j of records) {
    if (j.kind !== 'sign-off') continue
    const prev = by[j.subject]
    if (!prev || j.date > prev.date || (j.date === prev.date && j.id > prev.id)) by[j.subject] = j
  }
  return by
}

// One condition — { fact, op, value } -> { fired: true|false|null, note } where
// null means the fact path did not resolve (surfaced, never guessed).
export function evalCondition(cond, facts) {
  const got = getPath(facts, cond.fact)
  if (cond.op === 'exists') return { fired: got !== undefined, note: `${cond.fact} ${got !== undefined ? 'exists' : 'is absent'}` }
  if (cond.op === 'absent') return { fired: got === undefined, note: `${cond.fact} ${got === undefined ? 'is absent' : 'exists'}` }
  if (got === undefined) return { fired: null, note: `${cond.fact}: unresolvable fact path` }
  if (cond.op === 'eq') return { fired: deepEq(got, cond.value), note: `${cond.fact} = ${JSON.stringify(got)}` }
  if (cond.op === 'ne') return { fired: !deepEq(got, cond.value), note: `${cond.fact} = ${JSON.stringify(got)} (expected ${JSON.stringify(cond.value)})` }
  if (cond.op === 'gt' || cond.op === 'lt') {
    const comparable = (typeof got === 'number' && typeof cond.value === 'number') || (typeof got === 'string' && typeof cond.value === 'string')
    if (!comparable) return { fired: null, note: `${cond.fact}: ${cond.op} needs two numbers or two strings (got ${typeof got} vs ${typeof cond.value})` }
    return { fired: cond.op === 'gt' ? got > cond.value : got < cond.value, note: `${cond.fact} = ${JSON.stringify(got)}` }
  }
  return { fired: null, note: `unknown op '${cond.op}'` }
}

// Pure: one judgment against one facts view. facts.today is THE clock (expiry
// included) so overlays time-travel consistently. Findings carry machine identity:
//   { code: expired|drifted|tripped|unresolvable|advice, fact?, want?, got?, text }
export function evaluateJudgment(j, facts) {
  let verdict = 'ok'
  const findings = []
  const bump = (code, f) => { findings.push({ code, ...f }); if (ORDER[code] > (ORDER[verdict] ?? 0)) verdict = code }
  const today = facts.today
  if (!today) bump('unresolvable', { fact: 'today', text: 'facts.today missing — expiry not evaluable' })
  else if (j.review_by < today) bump('expired', { fact: 'review_by', want: `>= ${today}`, got: j.review_by, text: `review_by ${j.review_by} has passed — re-judge or retire` })
  for (const [k, want] of Object.entries(j.expected_state || {})) {
    const got = getPath(facts, k)
    if (got === undefined) bump('unresolvable', { fact: k, text: `expected_state ${k}: unresolvable fact path` })
    else if (!deepEq(got, want)) bump('drifted', { fact: k, want, got, text: `expected_state ${k}: assumed ${JSON.stringify(want)}, now ${JSON.stringify(got)}` })
  }
  if (j.tripwire) {
    const { fired, note } = evalCondition(j.tripwire, facts)
    if (fired === null) bump('unresolvable', { fact: j.tripwire.fact, text: `tripwire: ${note}` })
    else if (fired) bump('tripped', { fact: j.tripwire.fact, want: j.tripwire, got: getPath(facts, j.tripwire.fact), text: `tripwire fired: ${note} — the accepted world changed` })
  } else if (j.kind !== 'sign-off') {
    findings.push({ code: 'advice', text: 'no tripwire — nothing can void this automatically (add one)' })
  }
  if (j.kind === 'break-glass' && !j.gate) findings.push({ code: 'advice', text: 'break-glass without gate scope (admit|reconcile)' })
  return { id: j.id, kind: j.kind, subject: j.subject, verdict, findings }
}

// The facts view judgments reference (documented in CONTRACT.md): descriptor.* ·
// planes.{tree,history,forge}.* · git.{branch,head,shallow} · today. Meta keys
// (present/valid) win over descriptor fields by spread order — and the schema
// forbids fields by those names anyway. The forge probe is skipped unless asked
// for: it spawns gh (network); callers pass probeForge when a judgment (or no
// overlay) actually needs planes.forge. An optional overlay deep-merges last —
// fixtures now, M6's richer sweep facts later (src/facts/ is the eventual owner
// of this namespace once lane/PR facts join it at M5/M6).
export function gatherJdgFacts(REPO, { overlay = null, today, probeForge = true } = {}) {
  const repo = liteRepo(REPO)
  const d = loadDescriptor(repo)
  const cap = probeForge ? capabilityProbe(repo) : { tree: { available: true }, history: repo.HEAD ? { available: true, shallow: repo.gitIsShallow(), branch: currentLane(repo) } : { available: false, reason: 'not a git repository (no HEAD)' }, forge: { available: false, reason: 'not probed (no judgment references planes.forge)' } }
  const facts = {
    today,
    descriptor: { ...(d.valid ? d.data : {}), present: d.present, valid: d.valid },
    planes: cap,
    git: { branch: currentLane(repo), head: repo.HEAD, shallow: cap.history.available ? cap.history.shallow : false },
  }
  const merge = (into, from) => { for (const k of Object.keys(from)) { if (from[k] && typeof from[k] === 'object' && !Array.isArray(from[k]) && into[k] && typeof into[k] === 'object') merge(into[k], from[k]); else into[k] = from[k] } }
  if (overlay) merge(facts, overlay)
  return facts
}

const JDG_USAGE = `usage: baseline jdg new --kind K --subject S --reason "..." --review-by YYYY-MM-DD [--by W] [--expect path=json ...] [--tripwire "fact op [value]"] [--gate admit|reconcile]
         baseline jdg check [--repo DIR] [--json] [--facts FILE]`

export function runJdg(argv) {
  if (argv[0] === '--help' || argv[0] === '-h') { console.log(`baseline jdg — author/evaluate the judgment ledger\n  ${JDG_USAGE}`); return 0 }
  const sub = argv[0] && !argv[0].startsWith('-') ? argv[0] : null
  const rest = sub ? argv.slice(1) : argv
  const opt = makeOpt(rest), optText = makeOptText(rest), optAll = makeOptAll(rest)
  const usage = msg => { console.error(`baseline jdg: ${msg}\n  ${JDG_USAGE}`); return 2 }
  // a value flag followed by another flag (or nothing) is a mistake, not a value —
  // never let String(true) become a repo path, an author name, or a silent no-op
  for (const f of ['--repo', '--by', '--date', '--gate', '--kind', '--review-by', '--facts', '--from']) if (opt(f, null) === true) return usage(`${f} needs a value`)
  const REPO = path.resolve(String(opt('--repo', process.cwd())))
  const JSON_OUT = !!opt('--json', false)
  const now = nowUTC()
  if (!now) return usage('BASELINE_LOG_NOW is not a parseable instant')
  const today = now.toISOString().slice(0, 10)

  if (sub === 'check') {
    let overlay = null
    const factsFile = opt('--facts', null)
    if (typeof factsFile === 'string') {
      try { overlay = JSON.parse(fs.readFileSync(path.resolve(factsFile), 'utf8')) } catch (e) { return usage(`cannot read --facts file: ${e.message}`) }
    }
    const { records, findings } = loadJudgments(REPO)
    // the forge probe spawns gh — pay for it only when some judgment looks at it
    const needsForge = !overlay?.planes?.forge && records.some(j => JSON.stringify([j.tripwire ?? null, j.expected_state ?? null]).includes('planes.forge'))
    const facts = gatherJdgFacts(REPO, { overlay, today, probeForge: needsForge })
    const results = records.map(j => evaluateJudgment(j, facts))
    const bad = results.filter(r => r.verdict === 'tripped' || r.verdict === 'expired')
    const exit = (bad.length || findings.length) ? 1 : 0
    if (JSON_OUT) { console.log(JSON.stringify({ repo: REPO, results, findings, exit }, null, 2)); return exit }
    const ICON = { ok: '✓', drifted: '≈', unresolvable: '?', expired: '⏰', tripped: '✗' }
    console.log(`\n# Judgments — ${path.basename(REPO)} · ${records.length} record(s)${findings.length ? ` · ${findings.length} INVALID` : ''}\n`)
    if (!records.length && !findings.length) { console.log(`_no judgments recorded (${JUDGMENTS_DIR}/ empty or absent)_\n`); return 0 }
    for (const r of results) {
      console.log(`  ${ICON[r.verdict]} ${r.id}  ${r.kind.padEnd(15)} ${String(r.subject).slice(0, 40).padEnd(40)} ${r.verdict.toUpperCase()}`)
      for (const f of r.findings) console.log(`      ↳ ${f.text}`)
    }
    for (const f of findings) console.log(`  ! ${f.file}  INVALID — ${f.error}`)
    console.log(exit ? `\n✗ ledger unhealthy: ${bad.length} voided/expired, ${findings.length} invalid.\n` : `\n✓ ledger healthy.\n`)
    return exit
  }

  if (sub === 'new') {
    // --from DRAFT replays a scrub-blocked judgment verbatim (the non-lossy promise)
    let record
    const fromFile = opt('--from', null)
    if (typeof fromFile === 'string') {
      try { record = JSON.parse(fs.readFileSync(path.resolve(fromFile), 'utf8')) } catch (e) { return usage(`cannot read --from draft: ${e.message}`) }
    } else {
      const kind = opt('--kind', null)
      if (!KINDS.includes(kind)) return usage(`--kind must be one of ${KINDS.join('|')}`)
      const subject = optText('--subject', null)
      const reason = optText('--reason', null)
      const review_by = opt('--review-by', null)
      if (typeof subject !== 'string' || !subject.trim()) return usage('--subject is required (a rule id, a file, or a scope)')
      if (typeof reason !== 'string' || !reason.trim()) return usage('--reason is required — a judgment without a why is a rubber stamp')
      if (typeof review_by !== 'string') return usage('--review-by YYYY-MM-DD is required — every judgment expires (pick a real re-look date)')
      const gate = opt('--gate', null)
      if (kind === 'break-glass' && (gate !== 'admit' && gate !== 'reconcile')) return usage('break-glass requires --gate admit|reconcile (which fail-closed gate it relieves)')
      const by = String(opt('--by', null) || run('git', ['-C', REPO, 'config', 'user.name']) || '').trim()
      if (!by) return usage('--by is required (git user.name unset)')

      const expected_state = {}
      for (const kv of optAll('--expect')) {
        const i = kv.indexOf('='); if (i < 1) return usage(`--expect wants path=value (got '${kv}')`)
        const k = kv.slice(0, i), raw = kv.slice(i + 1)
        try { expected_state[k] = JSON.parse(raw) } catch { expected_state[k] = raw }
      }
      let tripwire
      const tw = optText('--tripwire', null)
      if (typeof tw === 'string') {
        // fact + op split on whitespace; the VALUE is the raw remainder verbatim —
        // collapsing inner whitespace would store a comparand the author never typed
        const m = tw.trim().match(/^(\S+)\s+(\S+)(?:\s+([\s\S]+))?$/)
        if (!m) return usage(`--tripwire wants "fact op [value]" (got '${tw}')`)
        const [, fact, op, rawVal] = m
        if (op === 'exists' || op === 'absent') { if (rawVal !== undefined) return usage(`tripwire op '${op}' takes no value`); tripwire = { fact, op } }
        else {
          if (rawVal === undefined) return usage(`tripwire op '${op}' needs a value`)
          let value; try { value = JSON.parse(rawVal) } catch { value = rawVal }
          tripwire = { fact, op, value }
        }
      } else if (kind !== 'sign-off') {
        console.error(`  note: no --tripwire — nothing can void this ${kind} automatically until its review_by`)
      }

      record = { record: 'judgment/1', id: 'JDG-0000', kind, date: typeof opt('--date', null) === 'string' ? opt('--date', null) : today, by, subject: subject.trim(), reason: reason.trim(), review_by }
      if (Object.keys(expected_state).length) record.expected_state = expected_state
      if (tripwire) record.tripwire = tripwire
      if (kind === 'break-glass') record.gate = gate
    }

    // number LAST (drafts renumber to the next free id), then validate the whole
    let names = []
    try { names = fs.readdirSync(path.join(REPO, JUDGMENTS_DIR)) } catch {}
    const max = names.reduce((m, f) => { const x = f.match(/^JDG-(\d{4})\.json$/); return x ? Math.max(m, parseInt(x[1], 10)) : m }, 0)
    record.id = `JDG-${String(max + 1).padStart(4, '0')}`
    const errors = validateRecord('judgment', record)
    if (errors.length) return usage(`record invalid: ${errors.join('; ')}`)

    const content = JSON.stringify(record, null, 2) + '\n'
    const allowIds = optAll('--allow')
    const allowReason = optText('--allow-reason', null)
    if (allowIds.length && (typeof allowReason !== 'string' || !allowReason.trim())) return usage('--allow requires --allow-reason "why this is not a secret"')
    let allowlist
    try {
      if (allowIds.length) addAllowlistEntries(REPO, allowIds, allowReason.trim(), today)
      allowlist = loadAllowlist(REPO).entries
    } catch (e) { return usage(e.message) }
    const { blocked, warned, allowed } = scan(content, { allowlist })
    if (blocked.length) {
      const draft = keepDraft(REPO, `rejected-jdg-${today}-${record.id}.json`, content)
      if (JSON_OUT) { console.log(JSON.stringify({ written: null, draft: draft.rel, blocked, warned, allowed }, null, 2)); return 1 }
      console.error(`✗ scrub blocked the judgment — nothing written under records/.`)
      for (const f of blocked) console.error(`    ${f.name}  (${f.masked})   id ${f.id}`)
      console.error(`  draft kept (NOT lost): ${draft.rel} — it contains the flagged content.`)
      if (!draft.ignored) console.error(`  ⚠ .baseline/cache/ is NOT gitignored in this repo — add it BEFORE committing anything:  echo '.baseline/cache/' >> .gitignore`)
      console.error(`  a judgment's reason should never carry a live secret — rotate it, edit the draft, rerun:  baseline jdg new --from ${draft.rel}`)
      console.error(`  false positive?  rerun with the dated judgment:  baseline jdg new --from ${draft.rel}${blocked.map(f => ` --allow ${f.id}`).join('')} --allow-reason "why this is not a secret"`)
      return 1
    }
    const rel = `${JUDGMENTS_DIR}/${record.id}.json`
    const abs = path.join(REPO, rel)
    try { fs.mkdirSync(path.dirname(abs), { recursive: true }) }
    catch (e) { return usage(e.code === 'EEXIST' || e.code === 'ENOTDIR' ? `cannot create ${JUDGMENTS_DIR}/ — a file exists where the directory belongs` : e.message) }
    try { fs.writeFileSync(abs, content, { flag: 'wx' }) }
    catch (e) { return usage(e.code === 'EEXIST' ? `${rel} already exists (parallel write?) — rerun to take the next number` : e.message) }
    if (JSON_OUT) { console.log(JSON.stringify({ written: rel, draft: null, blocked: [], warned, allowed }, null, 2)); return 0 }
    console.log(`✓ recorded ${rel}  (${record.kind} · ${record.subject} · review by ${record.review_by})`)
    for (const f of warned) console.log(`  ⚠ heuristic finding (written anyway): ${f.name} (${f.masked}) — silence: --allow ${f.id} --allow-reason "..."`)
    return 0
  }

  return usage(`unknown subcommand '${sub ?? ''}' (try: new, check)`)
}
