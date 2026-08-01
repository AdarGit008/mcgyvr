// `baseline scrub` — scan record content for secret shapes with the ONE scan API
// (src/scrub.mjs) that `baseline log`/`jdg new` and REC-02 share. Two modes:
//
//   baseline scrub <file...> [--repo DIR]          scan worktree files as given
//   baseline scrub --pushed SHA [--since SHA]      scan committed records/ blobs in a
//       [--repo DIR]                               push range (the pre-push hook's mode)
//
// --pushed walks EVERY commit in the range (rev-list + diff-tree), not just the
// endpoint diff — a secret added in one commit and removed in the next still rides
// the outgoing pack, so it still blocks. Without --since (a brand-new ref), or when
// --since doesn't resolve locally (an unfetched remote tip), the whole records/
// tree at --pushed is scanned instead — a loud, safe over-scan, never a silent
// wave-through. Any path under .baseline/cache/ in the push is a block by
// construction: that dir holds scrub-REJECTED drafts and must stay gitignored.
// A blob that cannot be read is a loud environment error (exit 2), never "clean".
// All content is decoded utf8 — the one decoding every scan() call site uses, so
// finding ids match across log/REC-02/hook surfaces.
//
// Deterministic findings exit 1 (the hook blocks the push); heuristics warn and
// never block (C34/C07). False positives get a dated allowlist judgment:
// --allow <finding-id> --allow-reason "...", the same surface as `baseline log`.
// Exit: 0 clean · 1 blocked · 2 usage/environment.
import fs from 'node:fs'
import path from 'node:path'
import { execFileSync } from 'node:child_process'
import { makeOpt, makeOptText, makeOptAll, nowUTC } from './util.mjs'
import { scan, loadAllowlist, addAllowlistEntries, ALLOWLIST_FILE, CACHE_DIR } from './scrub.mjs'

const SCRUB_USAGE = `usage: baseline scrub <file...> [--repo DIR]
         baseline scrub --pushed SHA [--since SHA] [--repo DIR]
         baseline scrub --allow ID --allow-reason "..." [--repo DIR]`

export function runScrub(argv) {
  if (argv.includes('--help') || argv.includes('-h')) { console.log(`baseline scrub — scan record content for secret shapes\n  ${SCRUB_USAGE}\n  exit: 0 clean · 1 blocked (deterministic finding) · 2 usage/environment`); return 0 }
  const opt = makeOpt(argv), optText = makeOptText(argv), optAll = makeOptAll(argv)
  const usage = msg => { console.error(`baseline scrub: ${msg}\n  ${SCRUB_USAGE}`); return 2 }
  for (const f of ['--repo', '--pushed', '--since', '--allow']) if (opt(f, null) === true) return usage(`${f} needs a value`)
  const REPO = path.resolve(String(opt('--repo', process.cwd())))
  const git = args => execFileSync('git', args, { cwd: REPO, stdio: ['ignore', 'pipe', 'ignore'], maxBuffer: 256 * 1024 * 1024 })
  const resolves = ref => { try { git(['cat-file', '-e', `${ref}^{commit}`]); return true } catch { return false } }

  // --allow writes the dated judgment and exits — the retry loop after a blocked push
  const allowIds = optAll('--allow')
  if (allowIds.length) {
    const reason = optText('--allow-reason', null)
    if (typeof reason !== 'string' || !reason.trim()) return usage('--allow needs --allow-reason "why this is not a secret"')
    if (allowIds.some(id => !/^scrub-[0-9a-f]{12}$/.test(id))) return usage(`--allow takes finding ids (scrub-<12 hex>, as printed by a scan)`)
    const today = (nowUTC() ?? new Date()).toISOString().slice(0, 10)
    let entries
    try { entries = addAllowlistEntries(REPO, allowIds, reason.trim(), today) } catch (e) { console.error(`baseline scrub: ${e.message}`); return 2 }
    console.log(`allowlisted ${allowIds.join(', ')} (${ALLOWLIST_FILE}, ${entries.length} entr${entries.length === 1 ? 'y' : 'ies'}) — commit it (git add ${ALLOWLIST_FILE}) and rerun`)
    return 0
  }

  const pushed = opt('--pushed', null)
  let targets // [{name, text}]
  let cacheHits = []
  if (pushed) {
    if (!resolves(pushed)) { console.error(`baseline scrub: --pushed ${String(pushed).slice(0, 12)} does not resolve to a commit here`); return 2 }
    let since = opt('--since', null)
    if (since && !resolves(since)) {
      // an unfetched remote tip (force-push from a fresh clone) must not brick the
      // push OR silently skip the scan: over-scan the whole tree instead, loudly
      console.error(`scrub: --since ${String(since).slice(0, 12)} not found locally (unfetched remote tip?) — scanning the full records/ tree at --pushed instead`)
      since = null
    }
    const SCOPES = ['records/', CACHE_DIR + '/']
    // path -> the commit whose blob we scan (newest occurrence wins is irrelevant:
    // we scan EVERY distinct blob of every touched path in the range, deduped)
    const blobs = new Map() // `${sha}:${path}` dedup by blob object id
    const listFailed = msg => { console.error(`baseline scrub: ${msg}`); return null }
    const collect = () => {
      if (since) {
        let commits
        try { commits = git(['rev-list', `${since}..${pushed}`]).toString('utf8').split('\n').filter(Boolean) } catch { return listFailed(`cannot list commits ${String(since).slice(0, 12)}..${String(pushed).slice(0, 12)}`) }
        for (const c of commits) {
          // -m: an evil merge's own edits appear against each parent; --root covers
          // a root commit; -z disables path quoting (café.md stays literal)
          let out
          try { out = git(['diff-tree', '--no-commit-id', '--name-only', '--diff-filter=d', '-r', '-m', '--root', '-z', c, '--', ...SCOPES]).toString('utf8') } catch { return listFailed(`cannot read commit ${c.slice(0, 12)}`) }
          for (const p of out.split('\0').filter(Boolean)) {
            // --diff-filter=d guarantees the path exists at c; a failure here is an
            // environment problem and must be loud, never a silently-unscanned blob
            let sha; try { sha = git(['rev-parse', `${c}:${p}`]).toString('utf8').trim() } catch { return listFailed(`could not resolve ${p} at ${c.slice(0, 12)} — NOT scanned`) }
            if (!blobs.has(sha)) blobs.set(sha, { path: p, at: c })
          }
        }
      } else {
        let out
        try { out = git(['ls-tree', '-r', '-z', pushed, '--', ...SCOPES]).toString('utf8') } catch { return listFailed(`cannot read tree at ${String(pushed).slice(0, 12)}`) }
        for (const line of out.split('\0').filter(Boolean)) {
          const m = line.match(/^\d+ blob ([0-9a-f]+)\t(.+)$/s)
          if (m && !blobs.has(m[1])) blobs.set(m[1], { path: m[2], at: pushed })
        }
      }
      return blobs
    }
    if (collect() === null) return 2
    cacheHits = [...new Set([...blobs.values()].map(b => b.path).filter(p => p.startsWith(CACHE_DIR + '/')))]
    targets = []
    for (const [sha, { path: p, at }] of blobs) {
      if (p.startsWith(CACHE_DIR + '/')) continue // blocked by presence below — content is rejected-by-construction
      let text
      try { text = git(['cat-file', 'blob', sha]).toString('utf8') }
      catch { console.error(`baseline scrub: could not read pushed blob ${p} at ${String(at).slice(0, 12)} — NOT scanned`); return 2 }
      targets.push({ name: p, text })
    }
    if (!targets.length && !cacheHits.length) { console.log(`scrub: no record content in the push range — clean`); return 0 }
  } else {
    // positionals = argv minus flags AND their values (a path named like a flag value must not double-count)
    const VALUE_FLAGS = new Set(['--repo', '--pushed', '--since', '--allow', '--allow-reason'])
    const files = []
    for (let i = 0; i < argv.length; i++) {
      const a = argv[i]
      if (a.startsWith('-')) {
        if (VALUE_FLAGS.has(a)) { i++; continue }
        return usage(`unknown flag '${a}' (to scan a file named like a flag, prefix it: ./${a})`)
      }
      files.push(a)
    }
    if (!files.length) return usage('give files to scan, or --pushed SHA')
    targets = []
    for (const f of files) {
      const abs = path.isAbsolute(f) ? f : path.resolve(process.cwd(), f)
      let text; try { text = fs.readFileSync(abs, 'utf8') } catch { console.error(`baseline scrub: cannot read ${f}`); return 2 }
      targets.push({ name: f, text })
    }
  }

  let allowlist = []
  try { allowlist = loadAllowlist(REPO).entries } catch (e) { console.error(`baseline scrub: ${e.message}`); return 2 }
  let blocked = 0, warned = 0, allowed = 0
  for (const p of cacheHits) { blocked++; console.error(`  BLOCK ${p} — ${CACHE_DIR}/ draft in the push (scrub-rejected content; remove it from history and keep .baseline/ gitignored)`) }
  for (const t of targets) {
    const res = scan(t.text, { allowlist })
    allowed += res.allowed.length
    for (const x of res.blocked) { blocked++; console.error(`  BLOCK ${t.name}:${x.line} ${x.name} (${x.masked}) [${x.id}]`) }
    for (const x of res.warned) { warned++; console.error(`  warn  ${t.name}:${x.line} ${x.name} (${x.masked}) [${x.id}]`) }
  }
  if (blocked) {
    console.error(`\nscrub: ${blocked} deterministic secret shape(s) — push blocked. Rotate/remove them, or for a true false-positive:\n  baseline scrub --allow <finding-id> --allow-reason "why it isn't a secret" --repo ${REPO}`)
    return 1
  }
  console.log(`scrub: ${targets.length} file(s) clean${warned ? ` (${warned} heuristic warning(s) — review, never blocks)` : ''}${allowed ? ` (${allowed} allowlisted)` : ''}`)
  return 0
}
