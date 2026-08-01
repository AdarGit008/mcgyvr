// The facts cache — .baseline/cache/facts.ndjson. Gitignored, rebuildable, and ADVISORY-ONLY:
// gates never read it (FS8). Its only readers are stale-fallback display paths (orient serving
// a bounded-stale view when the forge is unreachable). Each line is one observed value with its
// observed_at, so age is always decidable. Deferred to a later slice: an integrity hash and the
// per-machine shared XDG cache (F9). A cache write failure is never fatal.
import fs from 'node:fs'
import path from 'node:path'

const CACHE_REL = '.baseline/cache/facts.ndjson'
export const cachePath = (repo) => path.join(repo.REPO, CACHE_REL)

export function cacheWrite(repo, key, value) {
  try {
    const p = cachePath(repo)
    fs.mkdirSync(path.dirname(p), { recursive: true })
    fs.appendFileSync(p, JSON.stringify({ key, value, observed_at: new Date().toISOString() }) + '\n')
  } catch { /* advisory — never fatal */ }
}

// Latest cached entry for a key -> { value, observed_at, age_ms } or null.
export function cacheRead(repo, key) {
  try {
    const lines = fs.readFileSync(cachePath(repo), 'utf8').trim().split('\n')
    for (let i = lines.length - 1; i >= 0; i--) {
      const e = JSON.parse(lines[i])
      if (e.key === key) return { value: e.value, observed_at: e.observed_at, age_ms: Date.now() - new Date(e.observed_at).getTime() }
    }
  } catch {}
  return null
}
