// `baseline log` — write one scrubbed, schema-valid session record (the forensic
// tier, C06). The UX is pinned by the M4 ruling (#21): one command, lane/agent/
// timestamp derived, stdin accepted, never $EDITOR; a scrub block is NON-LOSSY —
// the draft survives under the cache dir and the exact rerun is printed, with
// inline `--allow <finding-id> --allow-reason "..."` writing the dated allowlist entry.
//
//   baseline log -m "what happened" [--next "the one next step"]
//     [--deadends "..."] [--lane L] [--agent A] [--repo DIR] [--json]
//     [--from FILE] [--allow ID ... --allow-reason "..."]
//
// Message: --from FILE > -m TEXT (or `-m -`) > piped stdin. A --from file whose
// frontmatter declares `record: session/1` is a saved draft (what a scrub block
// wrote) and is replayed verbatim — same started/lane/agent, so the path is
// stable across retries. Free-text flags (-m/--next/--deadends/--reason) consume
// the next argv even when it starts with '--' (prose is prose). No side effects
// (allowlist writes included) happen before the whole invocation validates.
// Lane = branch name (FS2 — the shared currentLane seam M5 will reuse); paths are
// collision-free by construction (CF1: <YYYY-MM-DD>-<HHMMSS>-<agent>.md, O_EXCL,
// no counters) and containment-checked under records/sessions/.
// Exit: 0 written · 1 scrub-blocked · 2 usage/environment.
import fs from 'node:fs'
import path from 'node:path'
import { makeOpt, makeOptText, makeOptAll } from './util.mjs'
import { currentLane, resolveAgent, run } from './probe.mjs'
import { validateRecord, parseFrontmatter, renderFrontmatter, sessionRelPath } from './records.mjs'
import { scan, loadAllowlist, addAllowlistEntries, keepDraft, ALLOWLIST_FILE, CACHE_DIR } from './scrub.mjs'
import { extractNext } from './facts/git.mjs'

const LOG_USAGE = `usage: baseline log -m "what happened" [--next "..."] [--deadends "..."] [--lane L] [--agent A] [--from FILE] [--allow ID --allow-reason "..."]`

export function runLog(argv) {
  if (argv[0] === '--help' || argv[0] === '-h') { console.log(`baseline log — write one scrubbed, schema-valid session record\n  ${LOG_USAGE}\n  exit: 0 written · 1 scrub-blocked · 2 usage/environment`); return 0 }
  // value flags refuse a '--'-leading next token (it's another flag); TEXT flags
  // consume it regardless — "-m '--started with a dash'" is a message, not flags
  const opt = makeOpt(argv), optText = makeOptText(argv), optAll = makeOptAll(argv)
  const usage = msg => { console.error(`baseline log: ${msg}\n  ${LOG_USAGE}`); return 2 }
  // a value flag followed by another flag (or nothing) is a mistake, not a value —
  // never let String(true) become the repo a record silently lands in
  for (const f of ['--repo', '--lane', '--agent', '--from']) if (opt(f, null) === true) return usage(`${f} needs a value`)
  const REPO = path.resolve(String(opt('--repo', process.cwd())))
  const JSON_OUT = !!opt('--json', false)
  const jsonOut = (obj, code) => { console.log(JSON.stringify({ written: null, draft: null, blocked: [], warned: [], allowed: [], ...obj }, null, 2)); return code }

  const allowIds = optAll('--allow')
  const reason = optText('--allow-reason', null)
  if (allowIds.length && (typeof reason !== 'string' || !reason.trim())) return usage('--allow requires --allow-reason "why this is not a secret" (allowlist entries are dated judgments; one flag name across log and jdg)')
  const now = process.env.BASELINE_LOG_NOW ? new Date(process.env.BASELINE_LOG_NOW) : new Date()
  if (isNaN(now)) return usage('BASELINE_LOG_NOW is not a parseable instant')
  const started = now.toISOString().replace(/\.\d{3}Z$/, 'Z')
  const today = started.slice(0, 10)

  // ---- resolve the message (never $EDITOR; no side effects yet) ----
  const fromFile = opt('--from', null)
  let mFlag = optText('-m', optText('--message', null))
  let message = null, replay = null
  if (typeof fromFile === 'string') {
    let raw; try { raw = fs.readFileSync(path.resolve(fromFile), 'utf8') } catch (e) { return usage(`cannot read --from file: ${e.message}`) }
    const parsed = parseFrontmatter(raw)
    if (parsed.fields?.record === 'session/1') replay = parsed
    else if (parsed.fields) return usage(`--from file has frontmatter but is not a session draft (record: ${parsed.fields.record ?? 'missing'})`)
    else message = raw.trim()
  } else if (mFlag === '-' || (mFlag == null && !process.stdin.isTTY)) {
    try { message = fs.readFileSync(0, 'utf8').trim() } catch { message = '' }
  } else if (typeof mFlag === 'string') {
    message = mFlag.trim()
  }
  if (replay == null && !message) return usage('no message — pass -m "...", pipe stdin, or --from FILE')

  // ---- derive lane / agent / fields (drafts replay verbatim — stable path) ----
  let fields, body
  if (replay) {
    ;({ fields, body } = replay)
  } else {
    const branch = currentLane({ REPO })
    const lane = typeof opt('--lane', null) === 'string' ? opt('--lane', null) : (branch && branch !== '(detached)' ? branch : null)
    if (!lane) return usage(`no lane resolvable (${branch === '(detached)' ? 'detached HEAD' : 'no git branch here'}) — pass --lane <name>`)
    const agent = resolveAgent(opt('--agent', null), REPO)
    fields = { record: 'session/1', lane, agent, started }
    const next = typeof optText('--next', null) === 'string' ? optText('--next', null).trim() : ''
    const deadends = typeof optText('--deadends', null) === 'string' ? optText('--deadends', null).trim() : ''
    body = `\n# Session — ${lane} — ${today}\n\n## Did\n${message}\n` +
      (deadends ? `\n## Dead ends\n${deadends}\n` : '') +
      `\n## Left open\nnext: ${next}\n`
  }

  const errors = validateRecord('session', fields)
  if (errors.length) return usage(`record invalid: ${errors.join('; ')}`)
  const content = renderFrontmatter(fields) + body
  const rel = sessionRelPath(fields)
  // a lane rides into the path — resolve and refuse anything that leaves records/sessions/
  const home = path.resolve(REPO, 'records', 'sessions') + path.sep
  if (!path.resolve(REPO, rel).startsWith(home)) return usage(`lane '${fields.lane}' escapes records/sessions/ — not a usable lane name`)

  // records/ lives under --repo; if that isn't the git toplevel, orient (which reads
  // the toplevel's records/) would never see this record — say so instead of splitting
  const top = run('git', ['-C', REPO, 'rev-parse', '--show-toplevel'])
  if (top && path.resolve(top) !== REPO) console.error(`  note: --repo is below the git toplevel (${top}) — records/ will live under --repo, where orient won't look`)

  // ---- everything validated: NOW the dated judgments may land, then the gate ----
  let allowlist
  try {
    if (allowIds.length) addAllowlistEntries(REPO, allowIds, reason.trim(), today)
    allowlist = loadAllowlist(REPO).entries
  } catch (e) { return usage(e.message) }

  // the write-time scrub gate: deterministic blocks, heuristic warns (C34/C07)
  const { blocked, warned, allowed } = scan(content, { allowlist })
  if (blocked.length) {
    const draft = keepDraft(REPO, `rejected-log-${sessionRelPath(fields).split('/').pop()}`, content)
    if (JSON_OUT) return jsonOut({ draft: draft.rel, blocked, warned }, 1)
    console.error(`✗ scrub blocked the record — nothing written under records/.`)
    for (const f of blocked) console.error(`    ${f.name}  line ${f.line}  (${f.masked}${f.count > 1 ? ` ×${f.count}` : ''})   id ${f.id}`)
    console.error(`  draft kept (NOT lost): ${draft.rel} — it contains the flagged content.`)
    if (!draft.ignored) console.error(`  ⚠ ${CACHE_DIR}/ is NOT gitignored in this repo — add it BEFORE committing anything:  echo '${CACHE_DIR}/' >> .gitignore`)
    console.error(`  real secret?  rotate it, edit the draft, rerun:  baseline log --from ${draft.rel}`)
    console.error(`  false positive?  rerun with the dated judgment:  baseline log --from ${draft.rel}${blocked.map(f => ` --allow ${f.id}`).join('')} --allow-reason "why this is not a secret"`)
    return 1
  }

  const abs = path.join(REPO, rel)
  try { fs.mkdirSync(path.dirname(abs), { recursive: true }) }
  catch (e) { return usage(e.code === 'EEXIST' || e.code === 'ENOTDIR' ? `cannot create ${path.dirname(rel)}/ — a file exists where the directory belongs` : e.message) }
  try { fs.writeFileSync(abs, content, { flag: 'wx' }) } // O_EXCL: CF1 forbids counters; same agent + same second = retry, honestly
  catch (e) { return usage(e.code === 'EEXIST' ? `record already exists at ${rel} (same second + agent) — retry` : e.message) }

  if (JSON_OUT) return jsonOut({ written: rel, warned, allowed }, 0)
  console.log(`✓ logged ${rel}`)
  for (const f of warned) console.log(`  ⚠ heuristic finding (written anyway): ${f.name} line ${f.line} (${f.masked}) — silence: --allow ${f.id} --allow-reason "..."`)
  for (const f of allowed) console.log(`  · allowed by ${ALLOWLIST_FILE}: ${f.name} (${f.date}: ${f.reason})`)
  const next = extractNext(content)
  if (next) console.log(`  next: ${next}`)
  return 0
}
