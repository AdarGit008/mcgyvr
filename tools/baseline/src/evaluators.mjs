// The ~41 declarative check kinds. makeEvalCheck(ctx) closes over the repo index,
// resolved config, and run flags; evalCheck(c, rule) -> {ok:true|false|null, detail, soft?, signoff?}.
// ok:null means "not evaluable here" and always tags SKIP — one broken rule can't take down the run.
import path from 'node:path'
import fs from 'node:fs'
import { execSync } from 'node:child_process'
import { DAY, asArr, parseDate, daysAgo, getPath, reOf, nonEmpty, stripLineComment, isAdrFile, statusOf, FRONTMATTER_RE, nowUTC, globToRe, issueOf, refs as issueRefs, closes as issueCloses } from './util.mjs'
import { DESCRIPTOR_FILE, DESCRIPTOR_SCHEMA } from './descriptor.mjs'
import { classifyPostureDiff } from './derive/posture.mjs'
import { scan, loadAllowlist } from './scrub.mjs'
import { loadClaims, CLAIM_RECORD_GLOB } from './claims.mjs'
import { extractNext } from './facts/git.mjs'
import { deriveDivergence } from './derive/divergence.mjs'
import { computeVendorLock, VENDOR_TREE, VENDOR_LOCK } from './gen.mjs'

const DIV_REF_CAP = 20 // a hostile next: line with dozens of #N must not fan out a forge query each

// Every check kind evalCheck() knows how to run. --self-check flags any rule referencing one not in here.
export const CHECK_KINDS = new Set(['any-of', 'implies', 'workflow-permissions', 'doc-code-age', 'any-file', 'grep', 'file-contains', 'json-field', 'command', 'adr-status', 'adr-forward-link', 'config-nonempty', 'required-files', 'doc-freshness', 'md-links', 'path-integrity', 'version-consistency', 'dockerfile-digest', 'claims-field', 'claims-citations', 'signoff', 'descriptor', 'descriptor-valid', 'records-append-only', 'records-scrub', 'records-one-home', 'vendored-lock', 'branch-session-record', 'branch-atomicity', 'lane-anchor', 'lane-next-filled', 'lane-namespace', 'lane-record-pushed', 'lane-lease', 'div-anchor-closed', 'div-next-closed', 'div-closes-closed', 'descriptor-change', 'merge-sister-dep', 'forge-protection', 'workflow-state'])

export function makeEvalCheck({ repo, cfg, NO_EXEC, JDGS, DESCRIPTOR, BRANCH = null, DEFAULT_BRANCH = null, LANEWORLD = null, ADMITWORLD = null }) {
  const { REPO, FILES, HEAD, match, read, readText, readRaw, gitCommitISO, gitObjExists, gitIsAncestor, gitIsShallow, gitNameStatus, gitDiffNames, gitBlobAt, gitCatFile } = repo
  // The lane rules diff against where the branch diverged: the descriptor-declared
  // default branch, preferring whichever of local/origin twin is NEWER (a stale
  // local default widens the branch diff with upstream-authored commits); an
  // undeclared or unresolvable base is a SKIP (never a guess against a wrong base).
  function baseRef() {
    if (!DEFAULT_BRANCH) return null
    const local = gitObjExists(`${DEFAULT_BRANCH}^{commit}`) ? DEFAULT_BRANCH : null
    const remote = gitObjExists(`origin/${DEFAULT_BRANCH}^{commit}`) ? `origin/${DEFAULT_BRANCH}` : null
    if (local && remote) return gitIsAncestor(local, remote) === 0 ? remote : local
    return local || remote
  }
  // The newest session record COMMITTED on this lane (added in base...HEAD, exactly
  // FLOW-02's presence definition) — its committed-blob content, so an uncommitted draft
  // in the worktree can't make FLOW-03/05/DIV-02 contradict FLOW-02 ("no record" +
  // "empty next:" + "unpushed" for one file that isn't committed). ->
  //   { rel, next } committed record found · null no committed record (FLOW-02's finding)
  //   · { unprovable: reason } base unresolvable (all three then SKIP the same way).
  function committedLog(branch) {
    const base = baseRef()
    if (!base) return { unprovable: `default branch '${DEFAULT_BRANCH}' not resolvable locally` }
    const added = gitDiffNames(`${base}...HEAD`, `records/sessions/${branch}/`, { addedOnly: true })
    if (added === null) return { unprovable: `diff ${base}...HEAD failed` }
    const md = added.filter(f => f.endsWith('.md')).sort()
    if (!md.length) return null
    const rel = md.at(-1)
    const raw = gitCatFile('HEAD', rel) ?? read(rel)
    return { rel, next: extractNext(raw || '') }
  }
  // one clock (util.nowUTC): the override is parsed + ISO-normalized so a
  // non-ISO-but-parseable BASELINE_LOG_NOW can't turn expiry comparisons into
  // lexicographic garbage; unparseable falls back to the wall clock — a scoring
  // run degrades to real time rather than crashing or silently lying
  const TODAY = (nowUTC() ?? new Date()).toISOString().slice(0, 10)
  function globsOf(c) { return c.globs_from_config ? cfg[c.globs_from_config] : (c.file_from_config ? cfg[c.file_from_config] : c.globs) }

  // Lane-residency (M5c review): the per-lane discipline (FLOW-01/02/03/05) is for LANES —
  // branches in the namespace. A declared-family branch (release/*, adopt/*) is a
  // legitimate non-lane: FLOW-04 confirms its placement and NOTHING else applies, so it
  // isn't wallpapered with anchor/record/push warns it can never satisfy. A stray outside
  // every family is FLOW-04's single finding (placement), not four. Only fires the SKIP
  // when a namespace IS declared and the branch is non-resident; no namespace → the M4c
  // behavior (these rules already handle an absent namespace themselves).
  const laneNs = DESCRIPTOR?.valid ? DESCRIPTOR.data?.lanes?.namespace : null
  const nonResidentLane = () => BRANCH && laneNs && !globToRe(laneNs).test(BRANCH)

  function evalCheck(c, rule) {
    const k = c.kind

    if (k === 'any-of') {
      const subs = (c.checks || []).map(sc => evalCheck(sc, rule))
      if (subs.some(s => s.ok === true)) return { ok: true, detail: (subs.find(s => s.ok === true).detail) }
      if (subs.some(s => s.ok === false)) return { ok: false, detail: subs.filter(s => s.ok === false).map(s => s.detail).slice(0, 2).join(' | ') || 'no alternative satisfied' }
      return { ok: null, detail: 'n/a (no applicable target)' }
    }

    if (k === 'implies') {
      const w = evalCheck(c.when, rule)
      if (w.ok !== true) return { ok: null, detail: 'n/a (' + (c.when_label || 'precondition') + ' not present)' }
      const th = evalCheck(c.then, rule)
      if (th.ok === true) return { ok: true, detail: th.detail }
      if (th.ok === false) return { ok: false, detail: c.then_fail_detail || th.detail }
      return { ok: null, detail: th.detail } // can't evaluate the requirement (e.g. no CI files) -> skip, don't warn
    }

    if (k === 'workflow-permissions') {
      const files = match(globsOf(c)); if (!files.length) return { ok: null, detail: 'no workflow files' }
      const bad = []
      const blockOf = (lines, i, indent) => { // collect the inline value or the following more-indented lines
        const inline = stripLineComment(lines[i]).replace(/^\s*permissions:\s*/, '').trim() // a trailing comment must NOT read as the value
        if (inline) return inline
        let b = ''
        for (let j = i + 1; j < lines.length; j++) { const ind = lines[j].match(/^(\s*)/)[1].length; if (lines[j].trim() && ind <= indent) break; b += stripLineComment(lines[j]) + '\n' }
        return b
      }
      const hasWriteAll = s => /write-all/.test(s)
      // quote-insensitive; ignore OIDC/provenance scopes (id-token, attestations) — they grant no repo-write power (the canonical trusted-publishing pattern)
      const grantsWrite = s => /:\s*['"]?write\b/.test(s.replace(/(id-token|attestations)\s*:\s*['"]?write\b['"]?/g, ''))
      for (const f of files) {
        const t = readText(f); if (t == null) continue
        const lines = t.split('\n')
        let topFound = false, jobPermFound = false
        for (let i = 0; i < lines.length; i++) {
          const top = lines[i].match(/^permissions:/)
          const job = lines[i].match(/^(\s+)permissions:/)
          if (top) {
            topFound = true
            const block = blockOf(lines, i, 0)
            if (hasWriteAll(block)) bad.push(`${f.split('/').pop()}: top-level permissions: write-all`)
            else if (grantsWrite(block)) bad.push(`${f.split('/').pop()}: top-level grants a write scope (top-level should be read)`)
          } else if (job) {
            jobPermFound = true
            const block = blockOf(lines, i, job[1].length)
            if (hasWriteAll(block)) bad.push(`${f.split('/').pop()}: a job grants permissions: write-all`) // scoped job write is fine; write-all is not
          }
        }
        if (!topFound && !jobPermFound) bad.push(`${f.split('/').pop()}: no permissions block anywhere (broad default token)`)
      }
      const uniq = [...new Set(bad)]
      return { ok: uniq.length === 0, detail: uniq.length ? uniq.slice(0, 3).join('; ') : `${files.length} workflow(s) least-privilege` }
    }

    if (k === 'doc-code-age') {
      const files = match(globsOf(c)); if (!files.length) return { ok: null, detail: 'no docs to scan' }
      const lag = cfg[c.lag_days_from_config] || 30
      const bad = []; let checked = 0
      for (const f of files) {
        const t = read(f) || ''
        const fm = t.match(FRONTMATTER_RE); if (!fm) continue
        const inline = fm[1].match(/(?:^|\n)\s*sources:\s*\[([^\]]*)\]/) // anchored so data_sources:/test_sources: don't collide
        const block = fm[1].match(/(?:^|\n)\s*sources:\s*\r?\n((?:\s*-\s*[^\n]+\r?\n?)+)/)
        const norm = s => s.replace(/\s+#.*$/, '').trim().replace(/['"]/g, '').replace(/^\.\//, '') // strip trailing comment + quotes + leading ./
        let srcGlobs = []
        if (inline) srcGlobs = inline[1].split(',').map(norm).filter(Boolean)
        else if (block) srcGlobs = block[1].split('\n').map(s => norm(s.replace(/^\s*-\s*/, ''))).filter(Boolean)
        if (!srcGlobs.length) continue
        const docAge = gitCommitISO(f); if (!docAge) continue // count only docs whose own git date resolved
        const srcFiles = match(srcGlobs)
        if (!srcFiles.length) { bad.push(`${f.split('/').pop()}: sources anchor resolves to no files (dangling — can't verify freshness)`); checked++; continue }
        checked++
        let newest = null, dated = 0
        for (const sf of srcFiles) { const d = gitCommitISO(sf); if (d) { dated++; if (!newest || d > newest) newest = d } }
        if (!dated) { bad.push(`${f.split('/').pop()}: anchored source(s) not committed — can't verify freshness`); continue } // untracked code can't read as "fresh"
        if (newest && (newest.getTime() - docAge.getTime()) / DAY > lag) bad.push(`${f.split('/').pop()}: code newer by ${Math.round((newest.getTime() - docAge.getTime()) / DAY)}d (>${lag})`)
      }
      if (!checked) return { ok: null, detail: 'no docs declare a frontmatter sources: list (opt-in)' }
      return { ok: bad.length === 0, detail: bad.length ? bad.slice(0, 3).join('; ') : `${checked} anchored doc(s) not lagging` }
    }

    if (k === 'any-file') {
      const files = match(globsOf(c), { tracked: !!c.tracked_only, exclude: c.allow, excludeGlobs: c.exclude_globs })
      if (c.mode === 'absent') return { ok: files.length === 0, detail: files.length ? 'found: ' + files.slice(0, 3).join(', ') + (files.length > 3 ? ` (+${files.length - 3})` : '') : 'none present (good)' }
      return { ok: files.length > 0, detail: files.length ? files.slice(0, 2).join(', ') + (files.length > 2 ? ` (+${files.length - 2})` : '') : 'none of: ' + asArr(globsOf(c)).slice(0, 5).join(', ') }
    }

    if (k === 'grep') {
      const files = match(globsOf(c), { tracked: !!c.tracked_only, excludeGlobs: c.exclude_globs })
      if (!files.length) return { ok: null, detail: 'no files to scan' }
      const re = reOf(c.pattern, c.flags); if (!re) return { ok: null, detail: 'bad regex in rule' }
      const rd = c.raw_scan ? readRaw : readText
      // strip_comments: drop # and // line-comments (quote-aware) before matching, so a narrative mention can't satisfy a "tool is invoked" grep
      const prep = c.strip_comments ? (t => t.split('\n').map(stripLineComment).join('\n')) : (t => t)
      if (c.mode === 'all') {
        const miss = files.filter(f => { const t = readText(f); return !(t && re.test(prep(t))) })
        return { ok: miss.length === 0, detail: miss.length ? `${miss.length} file(s) missing marker: ${miss.slice(0, 2).join(', ')}` : `all ${files.length} file(s) marked` }
      }
      const hit = files.filter(f => { const t = rd(f); return t && re.test(prep(t)) })
      const present = hit.length > 0
      if (c.mode === 'absent') return { ok: !present, detail: present ? `matched in ${hit.length} file(s): ${hit.slice(0, 2).join(', ')}` : 'pattern not found (good)' }
      return { ok: present, detail: present ? `matched in ${hit.length} file(s)` : 'pattern not found' }
    }

    if (k === 'file-contains') {
      const files = match(globsOf(c))
      if (!files.length) return c.null_if_absent ? { ok: null, detail: 'no matching file (skipped)' } : { ok: false, detail: 'file absent: ' + asArr(globsOf(c)).slice(0, 3).join(', ') }
      const re = reOf(c.pattern, c.flags); if (!re) return { ok: null, detail: 'bad regex in rule' }
      const good = files.filter(f => { const t = readText(f); return t && (!c.min_len || t.length >= c.min_len) && re.test(t) })
      if (good.length) return { ok: true, detail: `${good[0]} ok` }
      const short = files.filter(f => { const t = readText(f); return t && c.min_len && t.length < c.min_len })
      return { ok: false, detail: short.length ? `${short[0]} too short (<${c.min_len} chars)` : `${files[0]} present but missing required content` }
    }

    if (k === 'json-field') {
      const files = match(globsOf(c))
      if (!files.length) return { ok: null, detail: 'no ' + asArr(globsOf(c)).slice(0, 2).join('/') + ' present' }
      for (const f of files) {
        const t = read(f); if (!t) continue
        let data; try { data = JSON.parse(t) } catch { return { ok: false, detail: `${f} is not valid JSON` } }
        const v = getPath(data, c.path)
        if (c.assert === 'true') { if (v === true) return { ok: true, detail: `${f}: ${c.path}=true` } }
        else if (c.assert === 'nonempty') { if (nonEmpty(v)) return { ok: true, detail: `${f}: ${c.path} set` } }
        else if (c.assert === 'present') { if (v !== undefined && v !== null) return { ok: true, detail: `${f}: ${c.path} present` } }
        else if (c.equals !== undefined) { if (v === c.equals) return { ok: true, detail: `${f}: ${c.path}=${v}` } }
      }
      return { ok: false, detail: `${c.path} not satisfied in ${files.slice(0, 2).join(', ')}` }
    }

    if (k === 'command') {
      const cmd = cfg[c.run_from_config]
      if (!cmd) return { ok: false, soft: true, detail: `no ${c.run_from_config} configured — the crown check can't run; set it in baseline.config.json` }
      if (NO_EXEC) return { ok: null, detail: '--no-exec (would run: ' + cmd + (c.repeat ? ` x${c.repeat}` : '') + ')' }
      const times = c.repeat || 1
      try { for (let i = 0; i < times; i++) execSync(cmd, { cwd: REPO, timeout: cfg.command_timeout_ms, stdio: 'pipe' }); return { ok: true, detail: (times > 1 ? `exit 0 x${times}: ` : 'exit 0: ') + cmd } }
      catch (e) {
        const stderr = (e.stderr ? String(e.stderr) : '').trim(); const tail = stderr ? stderr.split('\n').slice(-2).join(' / ').slice(0, 120) : String(e.message).split('\n')[0].slice(0, 100)
        return { ok: false, detail: (e.killed ? 'timed out: ' : 'failed: ') + cmd + ' — ' + tail }
      }
    }

    if (k === 'adr-status') {
      const files = match(cfg[c.globs_from_config]).filter(isAdrFile); if (!files.length) return { ok: null, detail: 'no numbered ADR files found' }
      const allowed = /(proposed|accepted|superseded|deprecated|rejected|amended|draft|active)/i
      const bad = []
      for (const f of files) {
        const t = read(f) || ''
        const st = statusOf(t)
        if (!st || !allowed.test(st)) { bad.push(`${f.split('/').pop()}: no/invalid Status`); continue }
        if (/superseded|deprecated|replaced/i.test(st) && !/supersed(ed)?\s*by|replaced\s*by|→\s*adr|see\s+adr/i.test(t)) bad.push(`${f.split('/').pop()}: superseded w/o forward link`)
      }
      return { ok: bad.length === 0, detail: bad.length ? bad.slice(0, 3).join('; ') : `${files.length} decision doc(s) ok` }
    }

    if (k === 'adr-forward-link') {
      const files = match(cfg[c.globs_from_config]).filter(isAdrFile); if (!files.length) return { ok: null, detail: 'no numbered ADR files found' }
      const bad = []
      for (const f of files) {
        const t = read(f) || ''
        const sm = t.match(/supersed(?:ed)?\s*by[^\n]*?(?:adr[- ]?)?(\d{1,4})/i)
        if (!sm) continue
        const n = sm[1]
        const padded = new Set([n, n.padStart(2, '0'), n.padStart(3, '0'), n.padStart(4, '0')])
        const found = files.some(g => { const base = g.split('/').pop(); const nums = base.match(/\d{1,4}/); return nums && (padded.has(nums[0]) || padded.has(String(parseInt(nums[0], 10)))) && g !== f })
        if (!found) bad.push(`${f.split('/').pop()} → ADR ${n} (no such file)`)
      }
      return { ok: bad.length === 0, detail: bad.length ? bad.slice(0, 3).join('; ') : `forward-links resolve` }
    }

    if (k === 'config-nonempty') { const v = cfg[c.path]; const ne = nonEmpty(v); return { ok: ne, detail: ne ? 'declared' : `config.${c.path} empty` } }

    if (k === 'required-files') {
      const list = asArr(cfg[c.list_from_config])
      if (!list.length) return { ok: null, detail: `config.${c.list_from_config} empty (opt-in)` }
      const bad = []
      for (const p of list) { const t = read(p); if (t == null) bad.push(`${p} missing`); else if (t.trim().length === 0) bad.push(`${p} empty`) }
      return { ok: bad.length === 0, detail: bad.length ? bad.slice(0, 3).join('; ') : `${list.length} grounding doc(s) present` }
    }

    if (k === 'doc-freshness') {
      const files = match(globsOf(c))
      if (!asArr(cfg[c.globs_from_config]).length) return { ok: null, detail: `config.${c.globs_from_config} empty (opt-in)` }
      if (!files.length) return { ok: null, detail: 'no docs matched' }
      const win = cfg[c.within_days_from_config] || 180
      const bad = []
      for (const f of files) {
        const t = read(f) || ''
        const fm = t.match(FRONTMATTER_RE) // was LF-only here: a CRLF-saved doc was invisible to doc-freshness
        const body = fm ? fm[1] : t.slice(0, 400)
        const m = body.match(new RegExp(c.field + '\\s*[:=]\\s*([0-9]{4}-[0-9]{2}-[0-9]{2})', 'i'))
        if (!m) { bad.push(`${f.split('/').pop()}: no ${c.field}`); continue }
        const d = parseDate(m[1]); if (!d) { bad.push(`${f.split('/').pop()}: bad date`); continue }
        if (daysAgo(d) > win) bad.push(`${f.split('/').pop()}: ${Math.round(daysAgo(d))}d old (>${win})`)
      }
      return { ok: bad.length === 0, detail: bad.length ? bad.slice(0, 3).join('; ') : `${files.length} doc(s) fresh` }
    }

    if (k === 'md-links') {
      const files = match(globsOf(c))
      if (!files.length) return { ok: null, detail: 'no docs to scan' }
      const linkRe = /\[[^\]]*\]\(([^)]+)\)/g
      const broken = []
      for (const f of files) {
        const t = readText(f); if (!t) continue
        const dir = path.dirname(f)
        let m
        while ((m = linkRe.exec(t))) {
          let target = m[1].trim().split(/\s+/)[0] // drop optional "title"
          if (!target || /^(https?:|mailto:|tel:|#|data:|<)/i.test(target)) continue
          if (target.includes('{{') || target.includes('${')) continue
          target = target.replace(/[#?].*$/, '')
          if (!target) continue
          // root-absolute links (/docs/x.md) resolve against the repo root, GitHub-style
          const rel = target.startsWith('/')
            ? path.normalize(target.replace(/^\/+/, '')).split(path.sep).join('/')
            : path.normalize(path.join(dir, target)).split(path.sep).join('/')
          const onDisk = fs.existsSync(path.join(REPO, rel)) || FILES.includes(rel)
          if (!onDisk) broken.push(`${f}→${target}`)
        }
      }
      return { ok: broken.length === 0, detail: broken.length ? `${broken.length} broken: ` + broken.slice(0, 3).join(', ') : `${files.length} doc(s), links resolve` }
    }

    if (k === 'path-integrity') {
      const files = match(globsOf(c))
      if (!files.length) return { ok: null, detail: 'no docs to scan' }
      const tokRe = /`([^`]+)`/g
      const missing = []
      let checked = 0
      for (const f of files) {
        const t = readText(f); if (!t) continue
        let m
        while ((m = tokRe.exec(t))) {
          const tok = m[1].trim()
          if (!/^[\w./-]+$/.test(tok) || !tok.includes('/') || !/\.[a-z0-9]{1,5}$/i.test(tok)) continue
          checked++
          const rel = tok.replace(/^\.\//, '')
          if (!(fs.existsSync(path.join(REPO, rel)) || FILES.some(x => x.endsWith('/' + rel) || x === rel))) missing.push(`${f}: ${tok}`)
        }
      }
      if (!checked) return { ok: null, detail: 'no path-like symbols found' }
      return { ok: missing.length === 0, detail: missing.length ? `${missing.length} missing: ` + missing.slice(0, 3).join(', ') : `${checked} path ref(s) resolve` }
    }

    if (k === 'version-consistency') {
      // Compare only true single-value PINS across homes. Ranges (engines/requires-python) and CI test-matrices are NOT pins.
      const pins = { node: [], python: [], go: [] }
      const keyOf = (lang, major, minor) => lang === 'node' ? major : `${major}.${minor ?? '0'}`
      const addPin = (lang, val, where) => {
        if (val == null) return
        const s = String(val).trim()
        if (/[<>=^~|*x]|\s-\s|\|\|/i.test(s)) return // a range/constraint, not a pin
        const m = s.match(/(\d+)(?:\.(\d+))?/); if (!m) return
        pins[lang].push({ key: keyOf(lang, m[1], m[2]), raw: s.slice(0, 12), src: where })
      }
      const rd = f => (FILES.includes(f) ? read(f) : null)
      if (rd('.nvmrc')) addPin('node', rd('.nvmrc'), '.nvmrc')
      if (rd('.node-version')) addPin('node', rd('.node-version'), '.node-version')
      if (rd('.python-version')) addPin('python', rd('.python-version'), '.python-version')
      const gm = rd('go.mod'); if (gm) { const m = gm.match(/^go\s+([0-9.]+)/m); if (m) addPin('go', m[1], 'go.mod') }
      const tv = rd('.tool-versions'); if (tv) for (const line of tv.split('\n')) { const m = line.match(/^\s*(nodejs|node|python|golang|go)\s+([0-9][0-9.]*)/i); if (m) { const l = /node/i.test(m[1]) ? 'node' : /python/i.test(m[1]) ? 'python' : 'go'; addPin(l, m[2], '.tool-versions') } }
      for (const df of match(["**/Dockerfile", "**/Dockerfile.*", "**/*.Dockerfile"])) {
        const t = readText(df) || ''
        let m; const fre = /^FROM\s+(?:--\S+\s+)*(node|python|golang):([0-9]+(?:\.[0-9]+)?)/gmi
        while ((m = fre.exec(t))) { const l = /node/i.test(m[1]) ? 'node' : /python/i.test(m[1]) ? 'python' : 'go'; addPin(l, m[2], df.split('/').pop()) }
      }
      const problems = []; let compared = 0
      for (const lang of Object.keys(pins)) {
        const ds = pins[lang]; if (ds.length < 2) continue
        compared++
        if (new Set(ds.map(d => d.key)).size > 1) problems.push(`${lang}: ${ds.map(d => `${d.src}=${d.raw}`).join(', ')}`)
      }
      if (!compared) return { ok: null, detail: 'runtime pinned in <2 homes (nothing to cross-check)' }
      return { ok: problems.length === 0, detail: problems.length ? 'DRIFT ' + problems.slice(0, 2).join(' ; ') : `pins consistent across ${compared} language(s)` }
    }

    if (k === 'dockerfile-digest') {
      const files = match(globsOf(c))
      if (!files.length) return { ok: null, detail: 'no Dockerfile' }
      const bad = []
      for (const f of files) {
        const t = readText(f); if (!t) continue
        const stages = new Set()
        for (const line of t.split('\n')) {
          const fm = line.match(/^\s*FROM\s+(.*)$/i)
          if (!fm) continue
          const toks = fm[1].trim().split(/\s+/).filter(x => !x.startsWith('--')) // drop build flags like --platform=...
          const img = toks[0]; if (!img) continue
          const asIdx = toks.findIndex(x => x.toLowerCase() === 'as')
          const alias = asIdx >= 0 ? toks[asIdx + 1] : undefined
          if (alias) stages.add(alias.toLowerCase())
          if (stages.has(img.toLowerCase())) { if (alias) stages.add(alias.toLowerCase()); continue } // reference to a prior build stage
          if (/@sha256:[0-9a-f]{64}/i.test(img)) { if (alias) stages.add(alias.toLowerCase()); continue }
          bad.push(`${f.split('/').pop()}: FROM ${img}`)
          if (alias) stages.add(alias.toLowerCase())
        }
      }
      return { ok: bad.length === 0, detail: bad.length ? bad.slice(0, 3).join('; ') : `${files.length} Dockerfile(s) digest-pinned` }
    }

    if (k === 'claims-field' || k === 'claims-citations') {
      // records-only since M7b: exploded records/claims/CLM-*.json is the one home
      // the checker reads; a lingering legacy monolith is CLAIM-07's business.
      const loaded = loadClaims(repo, cfg)
      if (loaded.errors.length) return { ok: false, detail: loaded.errors.slice(0, 2).join('; ') + (loaded.errors.length > 2 ? ` (+${loaded.errors.length - 2})` : '') }
      let claims = loaded.claims
      if (!claims.length) return { ok: false, detail: loaded.legacyPresent ? `no claim records — legacy ${cfg.claims_file} is no longer read; run \`baseline gen migrate-claims\` (MIGRATION.md)` : `no claims found (${CLAIM_RECORD_GLOB})` }
      if (c.applies_to_types) claims = claims.filter(cl => c.applies_to_types.includes(String(cl.type || '').toLowerCase()))
      if (!claims.length) return { ok: null, detail: 'no claims of type ' + c.applies_to_types.join('/') }
      const bad = []
      for (const cl of claims) {
        const id = cl.slug || cl.id || (typeof cl.statement === 'string' ? cl.statement.slice(0, 24) : '?')
        if (k === 'claims-citations') {
          const cits = Array.isArray(cl.citations) ? cl.citations : (cl.citations == null ? [] : null)
          if (cits === null) { bad.push(`${id}: "citations" must be an array`); continue }
          for (const cit of cits) { if (!cit || typeof cit !== 'object' || !cit.url || !cit.supports_because) bad.push(`${id}: citation missing url/supports_because`) }
          continue
        }
        const v = cl[c.field]
        if (v == null || v === '') { bad.push(`${id}: no ${c.field}`); continue }
        if (c.enum && !c.enum.includes(String(v))) bad.push(`${id}: ${c.field}='${v}' not in {${c.enum.join('|')}}`)
        if (c.is_date) { const d = parseDate(v); if (!d) bad.push(`${id}: ${c.field} not a date`); else if (c.within_days_from_config && daysAgo(d) > cfg[c.within_days_from_config]) bad.push(`${id}: prior-art stale (${Math.round(daysAgo(d))}d > ${cfg[c.within_days_from_config]}d)`) }
        for (const rf of (c.also_require || [])) if (!cl[rf]) bad.push(`${id}: missing ${rf}`)
        if (c.require_if && String(v) === c.require_if.when_value && !cl[c.require_if.then_field]) bad.push(`${id}: ${c.field}=${v} needs ${c.require_if.then_field}`)
      }
      return { ok: bad.length === 0, detail: bad.length ? bad.slice(0, 3).join('; ') + (bad.length > 3 ? ` (+${bad.length - 3})` : '') : `${claims.length} claim(s) ok` }
    }

    if (k === 'signoff') {
      // the unified ledger (M4b; the ONLY path since M7b — the legacy signoff.json
      // read retired with the contraction): a kind=sign-off JDG whose subject is
      // this rule id satisfies it while unexpired — a lapsed one is honestly NOT
      // signed. MIGRATION.md re-mints surviving V1 entries as records.
      const j = JDGS && JDGS[rule.id]
      if (j) {
        if (j.review_by < TODAY) return { ok: false, detail: `sign-off ${j.id} lapsed (review_by ${j.review_by}) — re-judge: baseline jdg new`, signoff: true }
        return { ok: true, detail: `${j.id} by ${j.by} ${j.date} (review by ${j.review_by})` }
      }
      // parity with the claims pointer: a V1 repo staring at "no sign-off recorded"
      // with its old ledger sitting right there deserves the migration named
      if (FILES.includes('.project-baseline/signoff.json')) return { ok: false, detail: 'no sign-off recorded — legacy signoff.json is no longer read; re-mint: baseline jdg new (MIGRATION.md)', signoff: true }
      return { ok: false, detail: 'no sign-off recorded', signoff: true }
    }

    if (k === 'records-append-only') {
      // REC-01 (C12/CF7): prove from history that committed records were never edited.
      // Layer 1: any modify/delete/rename event under the scope is a finding (MDR).
      // Layer 2 (the evil-merge holes MDR can't see, because plain `git log` shows no
      // file changes for merge commits): (a) a path that was Added but neither exists
      // now nor has a D/R disposal event vanished inside a merge; (b) a still-present
      // path with no M/R event whose HEAD blob matches NO add-blob was edited inside
      // a merge. "Introduction" is deliberately the SET of add-blobs across full
      // history (--full-history: a side-branch-only add is invisible to the default
      // simplified walk, and two lanes adding the same path then resolving to one
      // side must not read as an edit). Deterministic; shallow history is a SKIP.
      const scope = c.path || 'records/'
      if (!HEAD) return { ok: null, detail: 'no commit history here (not a git repo, or no commits yet)' }
      if (gitIsShallow()) return { ok: null, detail: 'shallow clone — history truncated, append-only not provable' }
      const mdr = gitNameStatus('MDR', scope, { fullHistory: true })
      const adds = gitNameStatus('A', scope, { fullHistory: true })
      if (mdr === null || adds === null) return { ok: null, detail: 'git history unreadable' }
      const current = new Set(match([scope + '**'], { tracked: true }))
      if (!adds.length && !mdr.length && !current.size) return { ok: null, detail: `no committed records under ${scope} yet` }
      const bad = mdr.map(e => `${e.sha.slice(0, 7)} ${e.status === 'M' ? 'edited' : e.status === 'D' ? 'deleted' : 'renamed'} ${e.to || e.path}`)
      const touched = new Set(mdr.map(e => e.path))
      const addBlobs = new Map() // path -> Set of blob shas at each add
      for (const e of adds) { const b = gitBlobAt(e.sha, e.path); if (b) { if (!addBlobs.has(e.path)) addBlobs.set(e.path, new Set()); addBlobs.get(e.path).add(b) } }
      for (const [p, blobs] of addBlobs) {
        if (!current.has(p)) { if (!mdr.some(e => (e.status === 'D' || e.status === 'R') && e.path === p)) bad.push(`${p} vanished with no recorded delete (merge-hidden?)`); continue }
        if (touched.has(p)) continue // already reported above
        const now = gitBlobAt('HEAD', p)
        if (now && blobs.size && !blobs.has(now)) bad.push(`${p} content differs from its introduction with no recorded edit (merge-hidden?)`)
      }
      return { ok: bad.length === 0, detail: bad.length ? `${bad.length} mutation(s): ` + bad.slice(0, 3).join('; ') + (bad.length > 3 ? ` (+${bad.length - 3})` : '') : `${current.size} record(s), history append-only` }
    }

    if (k === 'records-scrub') {
      // REC-02 (C34): re-scan LANDED records with the one scan API the write gate
      // uses — blob content at HEAD, not the worktree ("what landed" must give the
      // same verdict on a dirty tree and in CI, or M7's promotion to blocker breaks
      // reproducibility). Deterministic signatures fail the rule (warn now; M7's
      // promotion is a pure severity flip); heuristic findings are soft — they stay
      // WARN even at blocker. A blob we cannot read is surfaced as unscanned, never
      // folded into the clean count.
      const files = match(c.globs || ['records/**'], { tracked: true })
      if (!files.length) return { ok: null, detail: 'no committed records to scan' }
      let allowlist = []
      try { allowlist = loadAllowlist(REPO).entries } catch (e) { return { ok: false, soft: true, detail: String(e.message).slice(0, 120) } }
      const det = [], heu = [], unscanned = []; let allowed = 0, scanned = 0
      for (const f of files) {
        const t = gitCatFile('HEAD', f)
        if (t == null) { unscanned.push(f); continue }
        scanned++
        const res = scan(t, { allowlist })
        allowed += res.allowed.length
        for (const x of res.blocked) det.push(`${f}:${x.line} ${x.name} (${x.masked}) [${x.id}]`)
        for (const x of res.warned) heu.push(`${f}:${x.line} ${x.name} (${x.masked}) [${x.id}]`)
      }
      const unscannedNote = unscanned.length ? ` — ${unscanned.length} record(s) UNSCANNED at HEAD (${unscanned.slice(0, 2).join(', ')}${unscanned.length > 2 ? ', …' : ''})` : ''
      if (det.length) return { ok: false, detail: `deterministic secret shape(s): ` + det.slice(0, 3).join('; ') + (det.length > 3 ? ` (+${det.length - 3})` : '') + unscannedNote }
      if (heu.length) return { ok: false, soft: true, detail: `heuristic finding(s): ` + heu.slice(0, 3).join('; ') + (heu.length > 3 ? ` (+${heu.length - 3})` : '') + unscannedNote }
      if (unscanned.length) return { ok: false, soft: true, detail: `${scanned} scanned clean, but ${unscannedNote.slice(3)}` }
      return { ok: true, detail: `${scanned} record(s) scrub-clean at HEAD` + (allowed ? ` (${allowed} allowlisted)` : '') }
    }

    if (k === 'records-one-home') {
      // REC-04 (C09, pinned warn-only per CF10): the same fact must not live in two
      // record homes — duplicate ids/slugs across record files, or the session
      // narrative kept in both the V2 home and the legacy prototype home.
      const bad = []
      const seen = new Map() // key -> first file
      const claim = (key, f) => { const prev = seen.get(key); if (prev && prev !== f) bad.push(`${key} in both ${prev} and ${f}`); else seen.set(key, f) }
      let any = false, unparseable = 0
      for (const [kind, glob] of [['JDG', 'records/judgments/*.json'], ['CLM', 'records/claims/*.json']]) {
        for (const f of match([glob])) {
          any = true
          const raw = read(f); if (raw == null) continue
          // BOM-tolerant: a BOM-prefixed duplicate must not escape the cross-check;
          // still-unparseable files are counted, not silently waved through
          let obj; try { obj = JSON.parse(raw.replace(/^\uFEFF/, '')) } catch { unparseable++; continue }
          if (obj.id) claim(`${kind} ${obj.id}`, f)
          if (kind === 'CLM' && obj.slug) claim(`slug '${obj.slug}'`, f)
        }
      }
      for (const f of match(cfg.decision_globs)) {
        const m = f.split('/').pop().match(/^ADR-?(\d{1,4})/i)
        if (m) { any = true; claim(`ADR ${String(parseInt(m[1], 10))}`, f) }
      }
      const v2Sessions = match(['records/sessions/**']), legacySessions = match(['docs/session-log/**'])
      if (v2Sessions.length || legacySessions.length) any = true
      if (v2Sessions.length && legacySessions.length) bad.push(`session narrative has two homes (records/sessions/ and docs/session-log/)`)
      if (!any) return { ok: null, detail: 'no records to cross-check' }
      const unpNote = unparseable ? ` (${unparseable} unparseable file(s) not cross-checked)` : ''
      return { ok: bad.length === 0, detail: bad.length ? bad.slice(0, 3).join('; ') + (bad.length > 3 ? ` (+${bad.length - 3})` : '') + unpNote : 'every record fact has one home' + unpNote }
    }

    if (k === 'vendored-lock') {
      // REC-06 (M7c, C26/S9): the vendored tree's pin. Same recompute `gen lock`
      // performs — one hash definition, two consumers (writer + verifier). SKIP
      // when the canonical tree is absent: a repo that doesn't vendor (or vendors
      // elsewhere) is outside the lock contract, never wallpapered. Unhashable
      // entries (symlinks, unreadable files) DEGRADE to a labeled WARN over the
      // readable set — a SKIP here would let one dangling symlink mask a real
      // concurrent skew (the fail-open the panel caught); the writer refuses the
      // same entries outright.
      const lock = computeVendorLock(repo.REPO, repo)
      if (!lock.files && !lock.unhashable.length) return { ok: null, detail: `no vendored tree at ${VENDOR_TREE}/ — nothing to pin` }
      const caveat = lock.unhashable.length ? ` — and ${lock.unhashable.length} entr${lock.unhashable.length === 1 ? 'y' : 'ies'} cannot be hashed (${lock.unhashable[0]}${lock.unhashable.length > 1 ? `, +${lock.unhashable.length - 1}` : ''}), so the pin cannot fully verify` : ''
      if (!lock.files) return { ok: false, detail: `vendored tree at ${VENDOR_TREE}/ has no hashable files${caveat}; fix the tree, then pin: baseline gen lock` }
      const raw = read(VENDOR_LOCK)
      if (raw == null) return { ok: false, detail: `vendored tree (${lock.files} files${lock.version ? `, ${lock.version}` : ''}) is unpinned — no ${VENDOR_LOCK}; pin it: baseline gen lock` }
      let pin = null
      try { pin = JSON.parse(raw.replace(/^\uFEFF/, '')) } catch {}
      if (!pin || typeof pin.tree_hash !== 'string' || typeof pin.version !== 'string') return { ok: false, detail: `${VENDOR_LOCK} is not a lock ({version, tree_hash}) — rewrite it: baseline gen lock` }
      if (pin.tree_hash !== lock.tree_hash) {
        // the ruled skew finding names BOTH versions — equal strings still name
        // both honestly, with the benign-vs-not causes spelled out
        const equal = pin.version === (lock.version ?? '') ? ` (same version both sides: a hand-edit, or an EOL-converting checkout missing the vendored .gitattributes)` : ''
        return { ok: false, detail: `vendored tree skews from its lock: lock pins ${pin.version} (${pin.tree_hash.slice(0, 12)}), tree is ${lock.version ?? 'version unreadable'} (${lock.tree_hash.slice(0, 12)})${equal}${caveat} — re-vendor to match, or re-pin deliberately: baseline gen lock` }
      }
      if (lock.unhashable.length) return { ok: false, detail: `lock matches the readable set (${pin.version} · ${lock.files} files)${caveat}; remove the unhashable entr${lock.unhashable.length === 1 ? 'y' : 'ies'} and re-pin: baseline gen lock` }
      return { ok: true, detail: `pinned: ${pin.version} · ${lock.files} files · ${lock.tree_hash.slice(0, 12)}` }
    }

    if (k === 'branch-session-record') {
      // FLOW-02 (C14): work on a lane carries its own session record — the forensic
      // tier rides the same PR as the change it describes. Engine gates guarantee
      // this only runs on a non-default branch of a declared multi-lane repo.
      if (nonResidentLane()) return { ok: null, detail: `'${BRANCH}' is a declared-family / non-namespace branch — lane record discipline n/a (placement is FLOW-04's)` }
      const base = baseRef()
      if (!base) return { ok: null, detail: `default branch '${DEFAULT_BRANCH}' not resolvable locally — lane coupling not provable` }
      const changed = gitDiffNames(`${base}...HEAD`, null)
      if (changed === null) return { ok: null, detail: `diff ${base}...HEAD failed — lane coupling not provable` }
      // a freshly-cut lane with no work yet has nothing for a record to describe —
      // the record couples to the merge, not to branch creation (ceremony thinnest
      // where value is thinnest)
      if (!changed.length) return { ok: null, detail: 'no work on this branch yet — nothing for a record to describe' }
      const added = gitDiffNames(`${base}...HEAD`, `records/sessions/${BRANCH}/`, { addedOnly: true })
      if (added === null) return { ok: null, detail: `diff ${base}...HEAD failed — lane coupling not provable` }
      return { ok: added.length > 0, detail: added.length ? `${added.length} session record(s) ride this lane` : `no session record for lane '${BRANCH}' — write one: baseline log -m "..." --next "..."` }
    }

    if (k === 'branch-atomicity') {
      // FLOW-06 (C14/C26, heuristic per CF9): a branch changing a gated subject
      // should carry the corresponding record in the same range — same-PR atomicity.
      const base = baseRef()
      if (!base) return { ok: null, detail: `default branch '${DEFAULT_BRANCH}' not resolvable locally` }
      const changed = gitDiffNames(`${base}...HEAD`, null)
      if (changed === null) return { ok: null, detail: `diff ${base}...HEAD failed` }
      const hits = globs => { const res = asArr(globs).map(globToRe); return changed.some(f => res.some(re => re.test(f))) }
      const bad = []; let triggered = 0
      for (const p of (c.pairs || [])) {
        if (!hits(p.if_changed)) continue
        triggered++
        if (!hits(p.expect)) bad.push(p.note || `${asArr(p.if_changed).join(',')} changed without ${asArr(p.expect).join(',')}`)
      }
      if (!triggered) return { ok: null, detail: 'no gated subject changed on this branch' }
      return { ok: bad.length === 0, detail: bad.length ? bad.slice(0, 2).join('; ') : `${triggered} gated change(s) carry their record` }
    }

    if (k === 'descriptor') {
      // DESC-01 (narrowed at M7c): PRESENCE only — validity is DESC-02's blocker,
      // the FLOW-02/03 presence/content divide. One condition, one finding.
      const d = DESCRIPTOR
      if (!d || !d.present) return { ok: false, soft: true, detail: `no ${DESCRIPTOR_FILE} — the repo doesn't declare itself (type/lifecycle/maturity/workflow); copy a config-presets/*.repo.json posture preset` }
      if (!d.valid) return { ok: true, detail: `${DESCRIPTOR_FILE} present (schema validity is DESC-02's finding)` }
      const x = d.data
      return { ok: true, detail: `type=${x.type} · ${x.lifecycle}/${x.maturity} · workflow=${x.workflow} · anchoring=${x.anchoring}` }
    }

    if (k === 'descriptor-valid') {
      // DESC-02 (M7c, the M7b panel's filing): present-but-invalid at BLOCKER. Ten
      // workflow-gated blockers hang off this file — invalidity flips the posture
      // off (every gated rule SKIPs 'workflow contract off'), so the collapse must
      // be the loudest row in the run, not a warn beside a wall of skips. Absence
      // is DESC-01's (no overlap).
      const d = DESCRIPTOR
      if (!d || !d.present) return { ok: null, detail: `no ${DESCRIPTOR_FILE} — absence is DESC-01's finding` }
      if (!d.valid) return { ok: false, detail: `${DESCRIPTOR_FILE} invalid: ${d.errors.slice(0, 2).join('; ')}${d.errors.length > 2 ? ` (+${d.errors.length - 2} more)` : ''} — the posture is OFF while this file is broken (every workflow-gated blocker skips); fix the errors or re-copy a preset (retired owner key? MIGRATION.md)` }
      return { ok: true, detail: `${DESCRIPTOR_FILE} schema-valid (schema_version ${d.data.schema_version})` }
    }

    // ---- M5c lane/divergence kinds — every one reads through LANEWORLD (the SAME
    // gathering + derivation orient and reclaim use; one answer, three surfaces), and
    // every unreachable plane degrades to ok:null with the reason — exit-stable offline,
    // with multi-lane-local runs carrying makeForge's posture label, never fake
    // unreachability. A DIV finding sets res.diverged — the engine's DIVERGED tag. ----

    if (k === 'lane-anchor') {
      // FLOW-01: anchoring per the descriptor knob — existence + resolution ONLY
      // (open-ness is DIV-01's alone; overlap would double-report one contradiction)
      if (nonResidentLane()) return { ok: null, detail: `'${BRANCH}' is a declared-family / non-namespace branch — anchoring n/a (placement is FLOW-04's)` }
      const knob = DESCRIPTOR?.valid ? DESCRIPTOR.data.anchoring : null
      if (!knob || knob === 'off') return { ok: null, detail: 'anchoring off (descriptor anchoring: off)' }
      const w = LANEWORLD()
      if (!w.ns) return { ok: null, detail: 'no lanes.namespace declared — an anchor is underivable' }
      const n = issueOf(w.ns, BRANCH)
      if (n == null) return { ok: false, detail: `branch '${BRANCH}' carries no issue anchor under '${w.ns}' — claim lanes: baseline lane claim <issue>` }
      if (knob === 'relaxed') return { ok: true, detail: `anchored to #${n} (relaxed: existence only)` }
      if (!w.forge.available) return { ok: null, detail: `anchor #${n} unverifiable (${w.forge.reason}) — strict anchoring not provable` }
      const st = w.issueState(n)
      // unresolvable ≠ resolved-to-a-miss: a null from a transient query failure must
      // SKIP (parity with DIV-01's "never guessed"), never brand a real anchor bogus.
      // A resolved answer — open OR closed — proves the anchor exists (open-ness is DIV's).
      return st === 'unknown'
        ? { ok: null, detail: `anchor #${n} state unresolvable (missing issue or query failed) — strict anchoring not provable, never guessed` }
        : { ok: true, detail: `anchored to #${n} (${st})` }
    }

    if (k === 'lane-next-filled') {
      // FLOW-03: fires ONLY on a present record with an empty next: — absence of the
      // record itself is FLOW-02's finding (no overlap, no double report)
      if (nonResidentLane()) return { ok: null, detail: `'${BRANCH}' is a declared-family / non-namespace branch — lane record discipline n/a (placement is FLOW-04's)` }
      const log = committedLog(BRANCH)
      if (log?.unprovable) return { ok: null, detail: `lane coupling not provable — ${log.unprovable}` }
      if (!log) return { ok: null, detail: `no committed session record on this lane yet (absence is FLOW-02's)` }
      return log.next
        ? { ok: true, detail: `next: recorded (${log.rel})` }
        : { ok: false, detail: `${log.rel} has an empty next: — record the one next step (baseline log ... --next "...")` }
    }

    if (k === 'lane-namespace') {
      // FLOW-04: branch placement against the declared inventory — lanes.namespace +
      // lanes.families (the repo's REAL branch families, so legitimate release/adopt
      // branches are declared, not wallpapered). THE placement rule — not residency-gated.
      const w = LANEWORLD()
      if (!w.ns) return { ok: null, detail: 'no lanes.namespace declared' }
      const pools = [w.ns, ...w.families]
      const hit = pools.find(g => globToRe(g).test(BRANCH))
      return hit
        ? { ok: true, detail: `'${BRANCH}' sits in declared family '${hit}'` }
        : { ok: false, detail: `branch '${BRANCH}' is outside every declared family (${pools.join(' · ')}) — claim a lane (baseline lane claim) or declare the family (lanes.families)` }
    }

    if (k === 'lane-record-pushed') {
      // FLOW-05: the arbitrated threshold-free predicate — the newest COMMITTED session
      // record exists locally but is absent at origin (session-boundary-aligned; zero
      // tuning surface). Judged against the last-fetched origin state, and says so.
      if (nonResidentLane()) return { ok: null, detail: `'${BRANCH}' is a declared-family / non-namespace branch — push discipline n/a (placement is FLOW-04's)` }
      const log = committedLog(BRANCH)
      if (log?.unprovable) return { ok: null, detail: `push discipline not provable — ${log.unprovable}` }
      if (!log) return { ok: null, detail: 'no committed session record on this lane yet — nothing to push' }
      if (!gitObjExists(`origin/${BRANCH}^{commit}`)) return { ok: null, detail: `origin/${BRANCH} unknown locally — push discipline not provable (push/fetch first)` }
      return gitBlobAt(`origin/${BRANCH}`, log.rel) !== null
        ? { ok: true, detail: `newest record ${log.rel} is at origin (as of the last fetch)` }
        : { ok: false, detail: `newest session record ${log.rel} exists locally but is absent at origin/${BRANCH} (as of the last fetch) — push the lane before pausing` }
    }

    if (k === 'lane-lease') {
      // FLOW-07: lease liveness — warns ONLY at derived ABANDONED (C31; STALE is
      // orient's nudge, not a finding — the ruling forbids wallpaper)
      const w = LANEWORLD()
      if (!w.ns) return { ok: null, detail: 'no lanes.namespace declared' }
      const me = w.lanes.find(l => l.ref === BRANCH)
      if (!me) return { ok: null, detail: w.source ? `'${BRANCH}' is not a claimed lane at origin — lease n/a (claim it: baseline lane claim)` : `lanes underived: ${w.reason}` }
      if (me.state === 'COMPLETED') return { ok: null, detail: 'lane complete (tip merged into the default branch) — lease n/a; prune the branch' }
      if (me.state === null) return { ok: null, detail: me.labels.find(l => /underived/.test(l)) || 'lease underived' }
      // the git-plane low-confidence provenance (committer clock, no PR corroboration)
      // rides the detail — CONTRACT promises it "says so", and orient already shows it
      const prov = me.source === 'git' ? ' · git plane, committer clock (low confidence)' : ''
      if (me.state === 'ABANDONED') return { ok: false, detail: `lease ABANDONED (${Math.floor((me.age_ms ?? 0) / DAY)}d idle of ttl ${w.ttl})${prov} — renew (push work) or hand it over (baseline lane reclaim)` }
      return { ok: true, detail: `lease ${me.state} (${Math.floor((me.age_ms ?? 0) / 3600000)}h idle of ttl ${w.ttl})${prov}` }
    }

    // ---- DIV kinds: all three route their classification through deriveDivergence (the
    // ONE definition of a cross-tier contradiction) — the evaluator only gathers the
    // scoped facts, resolves availability, and presents the fix. res.diverged → DIVERGED.

    if (k === 'div-anchor-closed') {
      // DIV-01: issue-closed-lane-active — the work surface says in-progress, the
      // tracker says done; one of them lies.
      const w = LANEWORLD()
      if (!w.ns) return { ok: null, detail: 'no lanes.namespace declared' }
      const n = issueOf(w.ns, BRANCH)
      if (n == null) return { ok: null, detail: `'${BRANCH}' carries no issue anchor — nothing to diverge from (FLOW-01's territory)` }
      if (!w.forge.available) return { ok: null, detail: `anchor #${n} state unknown (${w.forge.reason}) — divergence not provable` }
      const st = w.issueState(n)
      if (st === 'unknown') return { ok: null, detail: `anchor #${n} state unresolvable — divergence not provable, never guessed` }
      // COMPLETED exemption (M7a): a merged lane's closed anchor is agreement
      const me = w.lanes.find(l => l.ref === BRANCH)
      const hit = deriveDivergence({ lanes: [{ ref: BRANCH, state: me?.state, anchor: { issue: n, state: st } }], issueStates: w.issueStates }).find(i => i.code === 'DIV-01')
      if (me?.state === 'COMPLETED' && !hit) return { ok: true, detail: `lane complete (tip merged into the default branch) — closed anchor #${n} is agreement; prune the branch` }
      return hit
        ? { ok: false, diverged: true, detail: `${hit.text} — the resolution path: reopen #${n} if the work is genuinely unfinished, or merge/close-and-prune the lane if it is done` }
        : { ok: true, detail: `anchor #${n} is open — lane and tracker agree` }
    }

    if (k === 'div-next-closed') {
      // DIV-02: a recorded next: naming a closed issue — the plan on disk is stale
      const w = LANEWORLD()
      const log = committedLog(BRANCH)
      if (log?.unprovable) return { ok: null, detail: `divergence not provable — ${log.unprovable}` }
      if (!log?.next) return { ok: null, detail: `no committed next: on this lane (FLOW-02/03's territory)` }
      const allRefs = issueRefs(log.next)
      if (!allRefs.length) return { ok: true, detail: 'next: names no issues — nothing to contradict' }
      if (!w.forge.available) return { ok: null, detail: `next: names #${allRefs.slice(0, DIV_REF_CAP).join(', #')} — states unknown (${w.forge.reason})` }
      const capped = allRefs.length > DIV_REF_CAP
      const scan = allRefs.slice(0, DIV_REF_CAP)
      for (const n of scan) w.issueState(n) // resolve into w.issueStates (memoized, capped)
      const hits = deriveDivergence({ thisLane: { branch: BRANCH, next: `#${scan.join(' #')}` }, issueStates: w.issueStates }).filter(i => i.code === 'DIV-02')
      const capNote = capped ? ` (+${allRefs.length - DIV_REF_CAP} more refs not checked)` : ''
      return hits.length
        ? { ok: false, diverged: true, detail: `next: points at closed issue(s) #${hits.map(h => h.issue).join(', #')} — the recorded plan is stale; re-derive (baseline orient) and re-log${capNote}` }
        : { ok: true, detail: `next:'s issue reference(s) #${scan.join(', #')} are open or unresolved — no contradiction proven${capNote}` }
    }

    if (k === 'div-closes-closed') {
      // DIV-03: done-with-nothing-merged — an open PR closing an already-closed issue
      const w = LANEWORLD()
      if (!w.forge.available) return { ok: null, detail: `${w.forge.reason} — PR closures unreadable` }
      const prs = w.prsOpenOrNull() // null-honest: a FAILED query must not read as "no PRs"
      if (prs === null) return { ok: null, detail: 'PR listing failed at the forge — closures unreadable (not "no PRs")' }
      if (!prs.length) return { ok: true, detail: 'no open PRs — nothing to diverge' }
      const scoped = prs.map(pr => ({ number: pr.number, branch: pr.headRefName, closes: issueCloses(pr.body) }))
      for (const pr of scoped) for (const n of pr.closes) w.issueState(n) // resolve, memoized
      const hits = deriveDivergence({ prs: scoped, issueStates: w.issueStates }).filter(i => i.code === 'DIV-03')
      return hits.length
        ? { ok: false, diverged: true, detail: `${hits.slice(0, 3).map(h => h.text).join('; ')}${hits.length > 3 ? ` (+${hits.length - 3})` : ''} — done-with-nothing-merged; retarget the PR or close it` }
        : { ok: true, detail: `${prs.length} open PR(s), none closes an already-closed issue` }
    }

    // ---- M6b: GOV-01/02 live asserts on the READABLE surface (the ruled ladder:
    // rules-for-branch is a plain read; the branch `protected` flag is plain; the
    // classic /protection endpoint needs admin and is consulted only under the
    // explicit BASELINE_GOV_ADMIN=1 opt-in). run() nulls every failure identically,
    // so 403-vs-down derives honestly: rules null while the branch's metadata
    // answers = unreadable WITH THIS TOKEN (SKIP, never source-loss); both null =
    // the forge plane degraded (the probe/posture reason rides the SKIP). The
    // `protected` flag reflects CLASSIC protection only — with the rules endpoint
    // unreadable, protected:false can NEVER assert "no protection" (a ruleset may
    // exist unseen), so that leg SKIPs rather than guessing. Deterministic: every
    // PASS/FAIL is a live boolean read of enforcement, not a grep of intent. ----

    if (k === 'forge-protection') {
      // subject guard BEFORE the world: LANEWORLD() forces the forge probe (3 gh
      // spawns), pure waste when the SKIP is already decided by an undeclared branch
      if (!DEFAULT_BRANCH) return { ok: null, detail: 'default branch undeclared (set ground_truth_boundary.default_branch) — protection has no subject' }
      const w = LANEWORLD ? LANEWORLD() : null
      if (!w) return { ok: null, detail: 'no lane world assembled — forge asserts n/a in this runner' }
      if (!w.forge.available) return { ok: null, detail: `protection unreadable (${w.forge.reason})` }
      const rules = w.forge.branchRules(DEFAULT_BRANCH)
      const meta = w.forge.branchMeta(DEFAULT_BRANCH)
      if (!Array.isArray(rules)) {
        // rules endpoint gave nothing — distinguish token-scoped denial from a dead plane
        if (meta) {
          if (c.gov === 'protection' && meta.protected === true) return { ok: true, detail: `classic branch protection active on ${DEFAULT_BRANCH} (rules endpoint unreadable with this token)` }
          return { ok: null, detail: `protection unreadable with this token (rules endpoint denied; ${DEFAULT_BRANCH} metadata readable${meta.protected === false ? ', protected flag false — but the flag cannot see rulesets, so absence is not provable' : ''})` }
        }
        return { ok: null, detail: w.forge.source === 'replay' ? 'protection unreadable (no branch-rules replay fixture)' : `protection facts unreadable (${w.forge.reason || 'forge queries failed'})` }
      }
      // Merge-PROTECTIVE rule types only: rulesets aggregate across layers (org+repo)
      // and carry non-merge rules too — a signatures-only or deletion-only ruleset
      // protects nothing GOV-01's title names, and a first-of-type .find would miss a
      // later layer's parameters, so every bit is checked with .some over ALL rules.
      const PROTECTIVE = new Set(['pull_request', 'required_status_checks', 'non_fast_forward', 'merge_queue'])
      const protective = [...new Set(rules.map(r => r.type))].filter(t => PROTECTIVE.has(t)).sort()
      if (c.gov === 'protection') {
        // GOV-01: is MERGE protection actually active on the default branch?
        if (protective.length) return { ok: true, detail: `active merge-protective rules on ${DEFAULT_BRANCH}: ${protective.join(', ')}` }
        const other = [...new Set(rules.map(r => r.type))].sort()
        const rulesNote = other.length ? `rules active (${other.join(', ')}) but none protects merges` : 'rules: none'
        if (meta?.protected === true) return { ok: true, detail: `classic branch protection active on ${DEFAULT_BRANCH} (${rulesNote})` }
        if (meta && meta.protected === false) return { ok: false, detail: `no active merge protection on ${DEFAULT_BRANCH} (${rulesNote}; protected flag false) — anyone can force-push or merge red; create a ruleset requiring the baseline checks` }
        return { ok: null, detail: `rules readable (${rulesNote}) but ${DEFAULT_BRANCH} metadata is not — classic protection state unknowable with this token` }
      }
      // GOV-02: strict up-to-date + conversation resolution — .some across EVERY rule
      // (layered rulesets enforce the union), classic ladder when rulesets lack the bits
      const strict = rules.some(r => r.type === 'required_status_checks' && r.parameters?.strict_required_status_checks_policy === true)
      const conv = rules.some(r => r.type === 'pull_request' && r.parameters?.required_review_thread_resolution === true)
      if (strict && conv) return { ok: true, detail: `ruleset on ${DEFAULT_BRANCH} enforces strict up-to-date checks and conversation resolution` }
      const missing = [!strict && 'strict up-to-date status checks (strict_required_status_checks_policy)', !conv && 'required conversation resolution (required_review_thread_resolution)'].filter(Boolean)
      if (meta?.protected === true) {
        // classic protection may enforce what the rulesets don't — never FAIL past it
        if (process.env.BASELINE_GOV_ADMIN) {
          const p = w.forge.branchProtection(DEFAULT_BRANCH)
          if (p) {
            const s = strict || p.required_status_checks?.strict === true
            const cv = conv || p.required_conversation_resolution?.enabled === true
            if (s && cv) return { ok: true, detail: `${DEFAULT_BRANCH} enforces strict up-to-date checks and conversation resolution (ruleset + classic, admin read)` }
            const still = [!s && 'strict up-to-date status checks', !cv && 'required conversation resolution'].filter(Boolean)
            return { ok: false, detail: `${DEFAULT_BRANCH} does not enforce: ${still.join(' + ')} (ruleset + classic read)` }
          }
          return { ok: null, detail: w.forge.source === 'replay' ? 'classic protection active but no branch-protection replay fixture' : `classic protection active but /protection denied even under BASELINE_GOV_ADMIN — the token is not admin on this repo` }
        }
        return { ok: null, detail: `ruleset lacks ${missing.join(' + ')} but classic protection is active — its settings need an admin token to read; opt in: BASELINE_GOV_ADMIN=1` }
      }
      if (meta && meta.protected === false) {
        return rules.length
          ? { ok: false, detail: `ruleset on ${DEFAULT_BRANCH} does not enforce: ${missing.join(' + ')} — a stale branch can merge green` }
          : { ok: false, detail: `no active protection on ${DEFAULT_BRANCH} — strict up-to-date and conversation resolution are unset` }
      }
      return { ok: null, detail: `rules readable but ${DEFAULT_BRANCH} metadata is not — classic protection state unknowable with this token` }
    }

    if (k === 'workflow-state') {
      // OPS-07 (M7c, falsifiable smallest shape): ONE recorded forge query of the
      // reconcile workflow's state. The subject is found in the TREE (a workflow
      // file invoking `baseline… reconcile`) — no workflow wired → SKIP, so repos
      // without the cron are never wallpapered. No run-age math, no constant, no
      // knob: `active` is alive, anything else (the disabled_* family — GitHub's
      // 60-day auto-disable is the named death mode) is a dead cron that will
      // never file the issues reconcile exists to file.
      const wfs = match(['.github/workflows/*.yml', '.github/workflows/*.yaml'])
        .filter(f => /baseline(\.mjs)?['"]?\s+reconcile\b/.test((read(f) || '').split('\n').map(stripLineComment).join('\n')))
        .sort()
      if (!wfs.length) return { ok: null, detail: 'no reconcile workflow in .github/workflows/ — the cron is not wired (nothing to be alive)' }
      const file = wfs[0].split('/').pop()
      const w = LANEWORLD ? LANEWORLD() : null
      if (!w) return { ok: null, detail: 'no lane world assembled — forge asserts n/a in this runner' }
      if (!w.forge.available) return { ok: null, detail: `workflow state unreadable (${w.forge.reason})` }
      const st = w.forge.workflowState(file)
      if (!st || typeof st.state !== 'string') return { ok: null, detail: w.forge.source === 'replay' ? `workflow state unreadable (no workflow-state replay fixture for ${file})` : `workflow state query failed for ${file} — liveness not provable, never guessed` }
      const extra = wfs.length > 1 ? ` (${wfs.length} reconcile workflows in tree — asserting the first, ${file})` : ''
      if (st.state === 'active') return { ok: true, detail: `${file}: active at the forge${extra}` }
      return { ok: false, detail: `${file}: ${st.state} at the forge — the cron files nothing while disabled${st.state === 'disabled_inactivity' ? ` (GitHub's 60-day auto-disable)` : ''}; re-enable: gh workflow enable ${file}${extra}` }
    }

    // ---- M6a admit-context kinds — both read through ADMITWORLD (the target-ref
    // world `baseline admit` assembles: target tip, range diff, added judgments,
    // sister lane refs). In any run without an ADMITWORLD they are unrepresentable
    // (contexts gating excludes them from check), and the guard keeps that honest. ----

    if (k === 'descriptor-change') {
      // DESC-03: a descriptor change in the admitted range carries its judgment in the
      // SAME range — subject exactly the descriptor filename (ONE spelling, the one
      // constant the tool owns; CONTRACT.md, FLOW-06's fix, and the jdg hint all emit
      // it). Deterministic: diff names + record subjects; the weakening classification
      // (x-strictness ladders + gate-consumed set-rules) rides the finding text — it is
      // M7's per-axis policy seam, not this verdict's fork.
      if (!ADMITWORLD) return { ok: null, detail: 'admit-context only (no target world assembled)' }
      const { targetRef, changed, addedJudgments, headDescriptor, jdgCapped } = ADMITWORLD
      if (changed === null) return { ok: null, detail: `diff ${targetRef}...HEAD failed — change scope unreadable (admit refuses on this as gating-source loss)` }
      // belt over the no-renames diff: a descriptor ABSENT at HEAD while the target has
      // a valid one IS a change, however the diff spelled it
      const touched = changed.includes(DESCRIPTOR_FILE) || !headDescriptor?.present
      if (!touched) return { ok: true, detail: `descriptor untouched in ${targetRef}...HEAD` }
      const weak = classifyPostureDiff(DESCRIPTOR?.valid ? DESCRIPTOR.data : null, headDescriptor?.valid ? headDescriptor.data : null, DESCRIPTOR_SCHEMA)
      const weakNote = weak.length ? ` — WEAKENING: ${weak.slice(0, 3).join('; ')}${weak.length > 3 ? ` (+${weak.length - 3} more)` : ''}` : ' (no posture axis weakened)'
      // M7a kind pin: {sign-off, deviation, risk-acceptance} satisfy — break-glass is
      // EXCLUDED (it is outage relief with its own gate semantics; letting it double
      // as descriptor-change approval would conflate the two valves M6 separated)
      const DESC_JDG_KINDS = ['sign-off', 'deviation', 'risk-acceptance']
      const jdgs = addedJudgments.filter(j => j.record && DESC_JDG_KINDS.includes(j.record.kind) && j.record.subject === DESCRIPTOR_FILE && j.record.review_by >= TODAY)
      if (!jdgs.length) {
        const kindMiss = addedJudgments.find(j => j.record && j.record.subject === DESCRIPTOR_FILE && j.record.review_by >= TODAY && !DESC_JDG_KINDS.includes(j.record.kind))
        const near = addedJudgments.filter(j => j.record && j.record.subject !== DESCRIPTOR_FILE)
        const hint = kindMiss ? ` (${kindMiss.record.id} rode this range with the right subject but kind '${kindMiss.record.kind}' — break-glass is outage relief, never descriptor-change approval; use ${DESC_JDG_KINDS.join('|')})`
          : near.length ? ` (a judgment rode this range but its subject is '${near[0].record.subject}', not '${DESCRIPTOR_FILE}' — the matcher is the exact filename)` : jdgCapped ? ` (judgment parsing capped at 500 added records — a qualifying one beyond the cap does not count; shrink the range)` : ''
        return { ok: false, detail: `${DESCRIPTOR_FILE} changed with no same-range judgment${weakNote}${hint} — baseline jdg new --kind deviation --subject "${DESCRIPTOR_FILE}" --reason "why the posture changed" --review-by <date>, in this PR` }
      }
      return { ok: true, detail: `descriptor change carries ${jdgs[0].record.id} (subject ${DESCRIPTOR_FILE}, review by ${jdgs[0].record.review_by})${weakNote}` }
    }

    if (k === 'merge-sister-dep') {
      // MERGE-02: a lane admitted atop ANOTHER lane's unmerged commits depends on work
      // that may never land (C32). Deterministic from the git plane alone: sister =
      // a local remote-tracking lane ref whose shared history with HEAD reaches past
      // the target tip. The Baseline-Stacked-On trailer (whole-token ref match in the
      // admitted range) declares the stack and lifts the finding. Blocker since M7a.
      if (!ADMITWORLD) return { ok: null, detail: 'admit-context only (no target world assembled)' }
      const { targetTip, headSha, sisters, stackedOn, mergeBase, sistersCapped } = ADMITWORLD
      const w = LANEWORLD()
      if (!w.ns) return { ok: null, detail: 'no lanes.namespace declared — sister lanes underivable' }
      if (!sisters.length) return { ok: true, detail: 'no sister lanes known locally (as of the last fetch)' }
      const deps = [], declared = []
      for (const s of sisters) {
        if (s.tip === headSha) continue // this PR's own lane seen under its remote-tracking name (a local branch-name mismatch is not a dependency)
        const mb = mergeBase('HEAD', s.tip)
        if (!mb) continue // no common history — unrelated lane
        if (gitIsAncestor(mb, targetTip) === 0) continue // shared history is already in the target
        ;(stackedOn.includes(s.ref) ? declared : deps).push(s.ref)
      }
      const capNote = sistersCapped ? ' (sister list capped at 100)' : ''
      if (deps.length) return { ok: false, detail: `HEAD contains unmerged commits from ${deps.join(', ')}${capNote} — land/rebase first, or declare the stack: trailer 'Baseline-Stacked-On: ${deps[0]}'` }
      if (declared.length) return { ok: true, detail: `stacked on ${declared.join(', ')} — declared via Baseline-Stacked-On${capNote}` }
      return { ok: true, detail: `no unmerged sister-lane dependencies (${sisters.length} sister(s) checked)${capNote}` }
    }

    return { ok: null, detail: 'unknown check kind: ' + k }
  }

  return evalCheck
}
