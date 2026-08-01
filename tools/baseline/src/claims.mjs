// Claims: ONE home since M7b — the per-claim records/claims/CLM-*.json (C17/C23).
// The V1 docs/CLAIMS.json monolith retired from the checker read with M7's
// contraction: the CLAIM rules evaluate records only, and an unmigrated monolith
// surfaces exactly twice — CLAIM-07 (the migration tripwire: monolith present at
// all = debt) and the empty-register detail below. `loadLegacyClaims` SURVIVES
// with one consumer, `gen migrate-claims` — MIGRATION.md's own executor; deleting
// it wholesale would kill the migration path the retirement depends on.
import { validateRecord } from './records.mjs'

export const CLAIM_RECORD_GLOB = 'records/claims/CLM-*.json'

// -> { claims: [{...claim, _file}], errors: ['file: why'] }. Unparseable or
// schema-invalid record files surface as errors (findings for the caller), never
// as silently-dropped claims.
export function loadClaimRecords(repo) {
  const claims = [], errors = []
  for (const f of repo.match(CLAIM_RECORD_GLOB)) {
    const raw = repo.read(f)
    if (raw == null) { errors.push(`${f}: unreadable`); continue }
    let obj
    try { obj = JSON.parse(raw) } catch { errors.push(`${f}: not valid JSON`); continue }
    const errs = validateRecord('claim', obj)
    if (errs.length) { errors.push(`${f}: ${errs[0]}${errs.length > 1 ? ` (+${errs.length - 1} more)` : ''}`); continue }
    claims.push({ ...obj, _file: f })
  }
  return { claims, errors }
}

// The V1 monolith reader — `gen migrate-claims`'s input, NOT a checker path.
// -> { present, claims, error }. present=false when the monolith doesn't exist;
// error set when it exists but can't be read as {claims:[...]}.
export function loadLegacyClaims(repo, cfg) {
  const f = cfg.claims_file
  if (!f || typeof f !== 'string') return { present: false, claims: [], error: null } // claims_file:false is absence, not JSON.parse(false)
  const raw = repo.read(f)
  if (raw == null) return { present: false, claims: [], error: null }
  let data
  try { data = JSON.parse(raw) } catch { return { present: true, claims: [], error: `${f}: not valid JSON` } }
  if (!Array.isArray(data.claims)) return { present: true, claims: [], error: `${f}: "claims" must be an array` }
  return { present: true, claims: data.claims.filter(cl => cl && typeof cl === 'object').map(cl => ({ ...cl, _file: f })), error: null }
}

// The view the CLAIM checks evaluate: records ONLY. legacyPresent is a bare
// tree fact (the monolith file exists — never parsed here), kept so the
// empty-register finding can point an unmigrated V1 repo at the migration
// instead of reporting "no claims" while its register sits in the old home.
export function loadClaims(repo, cfg) {
  const rec = loadClaimRecords(repo)
  const legacyPresent = typeof cfg.claims_file === 'string' && (repo.FILES.includes(cfg.claims_file) || repo.match(cfg.claims_file).length > 0)
  return { claims: rec.claims, recordCount: rec.claims.length, legacyPresent, errors: rec.errors }
}
