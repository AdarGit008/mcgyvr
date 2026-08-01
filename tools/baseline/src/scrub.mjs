// Scrub — the one scan API every layer shares (C34; layered honestly per F7/CF6/FS4).
// M4a wires the write-time gate inside `baseline log`; M4c adds the pre-push hook for
// hand-written records, the REC-02 rule (warn — REC promotion deferred by the M7 ruling), and the
// push-protection/gitleaks delegation check — all of them calling scan(), so there is
// exactly one opinion about what a secret looks like.
//
// Severity is honest (C07): DETERMINISTIC signatures (a match IS a secret shape — the
// SEC-01 set plus JWT and the fine-grained GitHub PAT) block a write; HEURISTIC shapes
// (assignments, high-entropy blobs) warn and never block. The allowlist
// (.baseline/scrub-allowlist.json) is itself a ledger of dated judgments (§5): each
// entry allows exactly one finding id — a content-derived hash, so moving the text
// around doesn't re-block, and the allowlist never stores the secret itself.
import fs from 'node:fs'
import path from 'node:path'
import crypto from 'node:crypto'
import { execFileSync } from 'node:child_process'

// SEC-01's exact signatures, split out; scrub and the rule set must never disagree
// about the deterministic tier.
const DETERMINISTIC = [
  { name: 'private-key-block',       re: () => /-----BEGIN (?:RSA|EC|OPENSSH|DSA|PGP)? ?PRIVATE KEY-----/g },
  { name: 'aws-access-key-id',       re: () => /AKIA[0-9A-Z]{16}/g },
  { name: 'google-api-key',          re: () => /AIza[0-9A-Za-z_-]{35}/g },
  { name: 'slack-token',             re: () => /xox[baprs]-[0-9A-Za-z-]{10,}/g },
  { name: 'github-token',            re: () => /gh[pousr]_[0-9A-Za-z]{36}/g },
  { name: 'github-fine-grained-pat', re: () => /github_pat_[0-9A-Za-z_]{22,}/g },
  { name: 'jwt',                     re: () => /eyJ[0-9A-Za-z_-]{8,}\.eyJ[0-9A-Za-z_-]{8,}\.[0-9A-Za-z_-]{8,}/g },
]

// Shape says "maybe": warn, never block. The entropy floor keeps 40-hex git SHAs
// (≤4 bits/char by alphabet) out of session logs' way — records talk about commits.
const HEURISTIC = [
  { name: 'secret-assignment', re: () => /(?:password|passwd|secret|api[_-]?key|auth[_-]?token|access[_-]?token|client[_-]?secret)\s*[:=]\s*['"][^'"\s]{8,}['"]/gi },
  { name: 'high-entropy-blob', re: () => /(?<![0-9A-Za-z+/=])[0-9A-Za-z+/]{38,64}(?![0-9A-Za-z+/=])/g, entropy: 4.5 },
]

// Introspectable copies of the deterministic signatures — the records suite pins
// each one as a substring of SEC-01's pattern, so scrub and the rule set cannot
// drift apart silently (the parity the module header promises, enforced).
export const DETERMINISTIC_SOURCES = DETERMINISTIC.map(p => ({ name: p.name, source: p.re().source }))

function shannon(s) {
  const freq = {}
  for (const ch of s) freq[ch] = (freq[ch] || 0) + 1
  let h = 0
  for (const k of Object.keys(freq)) { const p = freq[k] / s.length; h -= p * Math.log2(p) }
  return h
}

const mask = m => m.length <= 6 ? m[0] + '…' : m.slice(0, 4) + '…' + m.slice(-2)
export const findingId = (name, match) => 'scrub-' + crypto.createHash('sha256').update(name + ':' + match).digest('hex').slice(0, 12)

// scan(text, { allowlist }) -> { blocked, warned, allowed }
//   blocked  deterministic findings not allowlisted — the write must not happen
//   warned   heuristic findings not allowlisted — print, proceed
//   allowed  findings an allowlist entry covered (surfaced for transparency)
// Findings: { id, name, certainty, line, masked, count } — deduped by id; never the
// raw match (a scrub report must not itself leak what it caught).
export function scan(text, { allowlist = [] } = {}) {
  const allowedIds = new Map((allowlist || []).map(e => [e.id, e]))
  // newline offsets once per scan; line lookup is a binary search (no per-finding slicing)
  const nl = []
  for (let i = text.indexOf('\n'); i !== -1; i = text.indexOf('\n', i + 1)) nl.push(i)
  const lineAt = idx => { let lo = 0, hi = nl.length; while (lo < hi) { const mid = (lo + hi) >> 1; nl[mid] < idx ? lo = mid + 1 : hi = mid } return lo + 1 }
  const seen = new Map()
  const spans = []
  const collect = (tier, certainty) => {
    for (const pat of tier) {
      const re = pat.re()
      let m
      while ((m = re.exec(text))) {
        if (pat.entropy && (shannon(m[0]) < pat.entropy || !/[a-z]/.test(m[0]) || !/[A-Z]/.test(m[0]) || !/[0-9]/.test(m[0]))) continue
        // heuristics hunt what the signatures DIDN'T claim: a match overlapping a
        // deterministic span is suppressed, so one value never reports under two names
        if (certainty === 'heuristic' && spans.some(([a, b]) => m.index < b && a < m.index + m[0].length)) continue
        if (certainty === 'deterministic') spans.push([m.index, m.index + m[0].length])
        const id = findingId(pat.name, m[0])
        const prev = seen.get(id)
        if (prev) { prev.count++; continue }
        seen.set(id, { id, name: pat.name, certainty, line: lineAt(m.index), masked: mask(m[0]), count: 1 })
      }
    }
  }
  collect(DETERMINISTIC, 'deterministic')
  collect(HEURISTIC, 'heuristic')
  const blocked = [], warned = [], allowed = []
  for (const f of seen.values()) {
    if (allowedIds.has(f.id)) { allowed.push({ ...f, reason: allowedIds.get(f.id).reason, date: allowedIds.get(f.id).date }); continue }
    ;(f.certainty === 'deterministic' ? blocked : warned).push(f)
  }
  return { blocked, warned, allowed }
}

export const ALLOWLIST_FILE = '.baseline/scrub-allowlist.json'
export const CACHE_DIR = '.baseline/cache' // drafts + derived caches — must stay gitignored

// Tolerant read: absent file -> empty ledger. A corrupt file surfaces as a thrown
// Error with a fix-it message — callers map it to a usage/environment failure, so
// a merge-conflicted ledger is never mistaken for a scrub block (exit-code contract).
export function loadAllowlist(repoDir) {
  const p = path.join(repoDir, ALLOWLIST_FILE)
  if (!fs.existsSync(p)) return { entries: [] }
  let data
  try { data = JSON.parse(fs.readFileSync(p, 'utf8')) }
  catch { throw new Error(`scrub allowlist unreadable (${ALLOWLIST_FILE}): not valid JSON — fix or delete it`) }
  return { entries: Array.isArray(data.entries) ? data.entries : [] }
}

// Non-lossy blocks, one implementation: park the rejected content under the cache
// dir and report whether that dir is actually gitignored HERE (the draft holds the
// flagged content — a false "stays gitignored" claim is how secrets get committed).
export function keepDraft(REPO, name, content) {
  const rel = `${CACHE_DIR}/${name}`
  const abs = path.join(REPO, rel)
  fs.mkdirSync(path.dirname(abs), { recursive: true })
  fs.writeFileSync(abs, content)
  let ignored = false
  try { execFileSync('git', ['-C', REPO, 'check-ignore', '-q', rel], { stdio: 'ignore' }); ignored = true } catch {}
  return { rel, ignored }
}

// Every entry is a dated judgment: { id, reason, date }. Re-allowing an id updates
// its entry (one judgment per finding, latest wins) rather than stacking duplicates.
export function addAllowlistEntries(repoDir, ids, reason, date) {
  const p = path.join(repoDir, ALLOWLIST_FILE)
  const cur = loadAllowlist(repoDir)
  for (const id of ids) {
    const e = { id, reason, date }
    const i = cur.entries.findIndex(x => x.id === id)
    if (i >= 0) cur.entries[i] = e; else cur.entries.push(e)
  }
  fs.mkdirSync(path.dirname(p), { recursive: true })
  fs.writeFileSync(p, JSON.stringify({ _help: 'Dated scrub judgments: each entry allows exactly one finding id (a content-derived hash — the secret itself is never stored). Added via `baseline log/scrub --allow <id> --allow-reason "..."`.', entries: cur.entries }, null, 2) + '\n')
  return cur.entries
}
