// Rules loader — manifest + per-category modules (plan §7). rules.json holds the
// runner's identity (name/version/project_types/profiles) and the ordered module
// list; each rules/<cat>.json holds that category's rules. The split is what lets
// M5+ land new rule families (flow/merge/rec/div) as additive files instead of
// monolith edits. Paths resolve against this module's own URL — co-located with
// rules.json + rules/, never copied apart (same contract as check.mjs itself).
import fs from 'node:fs'

export function loadRules() {
  const read = rel => JSON.parse(fs.readFileSync(new URL(rel, import.meta.url), 'utf8'))
  const manifest = read('../rules.json')
  // fail LOUD, never green-by-omission: a manifest without modules (e.g. a stale
  // monolithic rules.json synced next to a new src/ — the exact skew the co-location
  // contract warns about) must not score zero rules and exit 0
  if (!Array.isArray(manifest.modules) || !manifest.modules.length) {
    throw new Error(`rules.json has no "modules" list — ${Array.isArray(manifest.rules) ? 'this is a pre-split monolithic rules.json next to a post-split runner; update the whole install together' : 'rule set not loadable'}`)
  }
  const rules = []
  for (const m of manifest.modules) {
    const mod = read('../' + m)
    if (!Array.isArray(mod.rules)) throw new Error(`rules module ${m}: no "rules" array`)
    rules.push(...mod.rules)
  }
  // a module on disk that the manifest doesn't list would exist-yet-never-run —
  // structurally impossible in the monolith, so keep it impossible here
  const listed = new Set(manifest.modules.map(m => m.split('/').pop()))
  const onDisk = fs.readdirSync(new URL('../rules/', import.meta.url)).filter(f => f.endsWith('.json'))
  const orphans = onDisk.filter(f => !listed.has(f))
  if (orphans.length) throw new Error(`rules/ module(s) not listed in rules.json "modules" (would silently never run): ${orphans.join(', ')}`)
  return { ...manifest, rules }
}
