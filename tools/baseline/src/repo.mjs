// Repo index + read + git helpers — the at-rest-tree and git-history seam.
// Everything the evaluators know about the target repo flows through here.
import fs from 'node:fs'
import path from 'node:path'
import { execSync, execFileSync } from 'node:child_process'
import { asArr, globToRe, parseDate } from './util.mjs'

const SKIP_DIRS = new Set(['node_modules', '.git', 'dist', 'build', '.turbo', 'coverage', '.next', '__pycache__', 'vendor', '.venv', 'venv'])

function walk(dir, base = dir, out = []) {
  let ents; try { ents = fs.readdirSync(dir, { withFileTypes: true }) } catch { return out }
  for (const e of ents) {
    if (SKIP_DIRS.has(e.name)) continue
    const full = path.join(dir, e.name)
    const rel = path.relative(base, full).split(path.sep).join('/')
    if (e.isDirectory()) walk(full, base, out)
    else out.push(rel)
  }
  return out
}

// The light handle for commands that don't need the tree walk (log/jdg): just
// enough of indexRepo's surface for loadDescriptor + capabilityProbe. One home —
// the third hand-rolled copy of this shim was the review's cue to name it.
export function liteRepo(REPO) {
  let HEAD = null
  try { HEAD = execFileSync('git', ['rev-parse', '--short', 'HEAD'], { cwd: REPO, stdio: ['ignore', 'pipe', 'ignore'] }).toString().trim() } catch {}
  return {
    REPO,
    HEAD,
    read: rel => { try { return fs.readFileSync(path.join(REPO, rel), 'utf8') } catch { return null } },
    gitIsShallow: () => { try { return execFileSync('git', ['rev-parse', '--is-shallow-repository'], { cwd: REPO, stdio: ['ignore', 'pipe', 'ignore'] }).toString().trim() === 'true' } catch { return false } },
  }
}

export function indexRepo(REPO) {
  const FILES = walk(REPO)

  // git-tracked set (for tracked_only checks); null when not a git repo.
  // -z: NUL-separated, unquoted — core.quotePath C-quotes non-ASCII names, and a
  // quoted string never matches the fs-walked FILES spelling (a café.md record
  // would silently fall out of every tracked_only scan, including REC-02's).
  let TRACKED = null
  try { TRACKED = new Set(execFileSync('git', ['ls-files', '-z'], { cwd: REPO, stdio: ['ignore', 'pipe', 'ignore'], maxBuffer: 64 * 1024 * 1024 }).toString('utf8').split('\0').filter(Boolean)) } catch {}
  let HEAD = null
  try { HEAD = execSync('git rev-parse --short HEAD', { cwd: REPO, stdio: ['ignore', 'pipe', 'ignore'] }).toString().trim() } catch {}

  // match globs against the repo, with optional tracked-only, allow (exclude) and exclude_globs
  function match(globs, { tracked = false, exclude = [], excludeGlobs = [] } = {}) {
    const pool = (tracked && TRACKED) ? [...TRACKED] : FILES
    const res = asArr(globs).map(globToRe)
    const exRes = [...asArr(exclude), ...asArr(excludeGlobs)].map(globToRe)
    return pool.filter(f => res.some(r => r.test(f)) && !exRes.some(r => r.test(f)))
  }
  const read = rel => { try { return fs.readFileSync(path.join(REPO, rel), 'utf8') } catch { return null } }
  // read for content scanning: skip large / binary files
  function readText(rel) {
    try {
      const full = path.join(REPO, rel)
      const st = fs.statSync(full)
      if (st.size > 512 * 1024) return null
      const buf = fs.readFileSync(full)
      if (buf.includes(0)) return null // binary
      return buf.toString('utf8')
    } catch { return null }
  }
  // raw read for security scans: DO NOT skip large/binary — a committed secret can hide in either
  function readRaw(rel) {
    try { const full = path.join(REPO, rel); if (fs.statSync(full).size > 8 * 1024 * 1024) return null; return fs.readFileSync(full, 'latin1') } catch { return null }
  }

  // filenames/sha are passed as literal argv (execFileSync, no shell) — never interpolate attacker-controlled paths into a shell string
  function gitCommitISO(rel) { try { const iso = execFileSync('git', ['log', '-1', '--format=%cI', '--', rel], { cwd: REPO, stdio: ['ignore', 'pipe', 'ignore'] }).toString().trim(); return parseDate(iso) } catch { return null } }
  function gitAgeDays(rel) { const d = gitCommitISO(rel); return d ? (Date.now() - d.getTime()) / 86400000 : null }
  function gitObjExists(ref) { try { execFileSync('git', ['cat-file', '-e', ref], { cwd: REPO, stdio: 'ignore' }); return true } catch { return false } }
  function gitIsAncestor(sha, of = 'HEAD') { try { execFileSync('git', ['merge-base', '--is-ancestor', sha, of], { cwd: REPO, stdio: 'ignore' }); return 0 } catch (e) { return e.status ?? 1 } }
  function gitIsShallow() { try { return execFileSync('git', ['rev-parse', '--is-shallow-repository'], { cwd: REPO, stdio: ['ignore', 'pipe', 'ignore'] }).toString().trim() === 'true' } catch { return false } }

  // History events for a path scope: git log --name-status filtered to the given
  // change types (e.g. 'MDR', 'A'), oldest first. -> [{sha, status, path, to}]
  // (to only on renames). Returns null when history is unreadable (not a repo).
  // quotePath=false keeps non-ASCII names literal so they match FILES/TRACKED
  // spelling; names containing a literal newline/quote stay C-quoted (pathological
  // — accepted residual, the -z log format can't be mixed with --format records).
  // fullHistory disables history simplification: an add that only ever lived on a
  // merged-in side branch is invisible to the default first-parent-simplified walk.
  function gitNameStatus(diffFilter, rel, { fullHistory = false } = {}) {
    let out
    try { out = execFileSync('git', ['-c', 'core.quotePath=false', 'log', '--reverse', ...(fullHistory ? ['--full-history'] : []), '--format=@%H', '--name-status', `--diff-filter=${diffFilter}`, '--', rel], { cwd: REPO, stdio: ['ignore', 'pipe', 'ignore'], maxBuffer: 64 * 1024 * 1024 }).toString('utf8') } catch { return null }
    const events = []; let sha = null
    for (const line of out.split('\n')) {
      if (line.startsWith('@')) { sha = line.slice(1); continue }
      const m = line.match(/^([AMDR])\d*\t([^\t]+)(?:\t(.+))?$/)
      if (m && sha) events.push({ sha, status: m[1], path: m[2], to: m[3] })
    }
    return events
  }
  // Files changed on this branch since it diverged (merge-base semantics), optionally
  // restricted to a path scope and to added-only. -> [paths] or null when the range
  // doesn't resolve (missing base ref, not a repo). -z: unquoted, NUL-separated.
  // noRenames (M6a): rename detection collapses D+A into R and --name-only then prints
  // only the post-image name — `git mv baseline.repo.json away.json` would read as
  // "descriptor untouched" to DESC-03. Admit's range reads disable detection so a
  // renamed-away gated file is honestly a delete + an add.
  function gitDiffNames(range, rel, { addedOnly = false, noRenames = false } = {}) {
    const args = ['diff', ...(noRenames ? ['--no-renames'] : []), '--name-only', '-z', ...(addedOnly ? ['--diff-filter=A'] : []), range, '--', ...(rel ? [rel] : ['.'])]
    try { return execFileSync('git', args, { cwd: REPO, stdio: ['ignore', 'pipe', 'ignore'], maxBuffer: 64 * 1024 * 1024 }).toString('utf8').split('\0').filter(Boolean) } catch { return null }
  }
  // Blob id of a path at a ref -> sha string or null. Used by the append-only proof
  // to compare a record's current content against its content at introduction.
  function gitBlobAt(ref, rel) {
    try { return execFileSync('git', ['rev-parse', `${ref}:${rel}`], { cwd: REPO, stdio: ['ignore', 'pipe', 'ignore'] }).toString().trim() } catch { return null }
  }
  // Blob CONTENT at a ref, decoded utf8 (the one decoding every scan() call site
  // uses — a finding id must hash the same bytes-as-text on every surface). null on
  // any failure; callers surface that as "unscanned", never fold it into "clean".
  function gitCatFile(ref, rel) {
    try { return execFileSync('git', ['cat-file', 'blob', `${ref}:${rel}`], { cwd: REPO, stdio: ['ignore', 'pipe', 'ignore'], maxBuffer: 256 * 1024 * 1024 }).toString('utf8') } catch { return null }
  }

  return { REPO, FILES, TRACKED, HEAD, match, read, readText, readRaw, gitCommitISO, gitAgeDays, gitObjExists, gitIsAncestor, gitIsShallow, gitNameStatus, gitDiffNames, gitBlobAt, gitCatFile }
}
