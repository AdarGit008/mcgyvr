// Config resolution: DEFAULTS -> auto-detected project_type -> baseline.config.json
// -> --config file -> --profile flags, then the baseline.repo.json descriptor's declared
// type overrides all of them (C39: the repo's claim about itself is root intent, not a
// guess). Also derives the claims opt-in and active profiles.
import fs from 'node:fs'
import path from 'node:path'
import { loadDescriptor } from './descriptor.mjs'
import { loadJudgments, selectSignoffs } from './jdg.mjs'
import { CLAIM_RECORD_GLOB } from './claims.mjs'

export function detectType(repo) {
  const { FILES } = repo
  if (FILES.includes('package.json')) return FILES.some(f => f.startsWith('services/') || f.startsWith('apps/') || f.startsWith('cmd/')) ? 'service' : 'node'
  if (FILES.includes('pyproject.toml') || FILES.some(f => /requirements.*\.txt$/.test(f))) return 'python'
  if (FILES.includes('go.mod')) return 'service'
  return 'docs'
}

export function buildDefaults(repo) {
  const firstExisting = (cands) => cands.find(c => repo.FILES.includes(c)) || cands[0]
  return {
    project_type: detectType(repo),
    makes_external_claims: true,
    bootstrap_command: null,
    command_timeout_ms: 600000,
    claims_file: 'docs/CLAIMS.json',
    decision_globs: ['docs/decisions/*.md', 'docs/adr/*.md', 'adr/*.md', 'docs/decisions/**/*.md', 'records/decisions/*.md'], // records/decisions/ is CONTRACT.md's V2 decision home — REC-04's cross-check must see it
    doc_globs: ['**/*.md'],
    sources_of_truth: {},
    prior_art_recheck_days: 90,
    doc_freshness_days: 180,
    doc_lag_days: 30,      // CTX-11: max days a doc may lag the code it anchors
    freshness_globs: [],   // opt-in: docs that must carry last_review_date
    generated_globs: [],   // opt-in: generated files that must carry a DO NOT EDIT marker
    grounding_docs: [],    // opt-in: required grounding docs (exist + non-empty)
    profiles: [],          // extra profiles beyond core (service auto-enables for services)
  }
}

export function resolveConfig(repo, { cliConfigPath = null, profileArgs = [], descriptorRef = null } = {}) {
  const DEFAULTS = buildDefaults(repo)
  let cfg = { ...DEFAULTS }
  const EXPLICIT = new Set()
  const applyCfg = obj => { for (const kk of Object.keys(obj)) if (!kk.startsWith('_')) EXPLICIT.add(kk); cfg = { ...cfg, ...obj } }
  const inRepoCfg = repo.read('baseline.config.json'); if (inRepoCfg) try { applyCfg(JSON.parse(inRepoCfg)) } catch {}
  if (cliConfigPath && typeof cliConfigPath === 'string') try { applyCfg(JSON.parse(fs.readFileSync(path.resolve(cliConfigPath), 'utf8'))) } catch (e) { console.error('bad --config:', e.message) }
  for (const p of profileArgs) cfg.profiles = [...(cfg.profiles || []), p]

  // The descriptor's declared type is the root identity fact (C39): a valid baseline.repo.json
  // supersedes both the filesystem auto-detection and any config project_type, so a repo whose
  // package.json is only for tooling isn't misclassified as node. Absent or invalid descriptor
  // -> auto-detect/config still governs (the ref seam lets M6 read it from the target branch).
  const DESCRIPTOR = loadDescriptor(repo, { ref: descriptorRef })
  if (DESCRIPTOR.valid && DESCRIPTOR.data.type) cfg.project_type = DESCRIPTOR.data.type

  // Claims are OPT-IN: whether a repo makes external claims isn't robot-detectable at rest.
  // Active only if a claims register is present (either home — the legacy monolith or the
  // exploded records/claims/), OR makes_external_claims was explicitly set true. The
  // descriptor's maturity gates activation (C24, discrete tiers per S8): a declared
  // 'prototype' repo isn't held to claims discipline unless it explicitly opted in —
  // drift climbs the stack as a project matures.
  const claimsRegisterExists = (repo.FILES.includes(cfg.claims_file) || repo.match(cfg.claims_file).length > 0 || repo.match(CLAIM_RECORD_GLOB).length > 0)
  let CLAIMS_ACTIVE = EXPLICIT.has('makes_external_claims') ? (cfg.makes_external_claims !== false) : claimsRegisterExists
  let CLAIMS_REASON = null
  if (CLAIMS_ACTIVE && DESCRIPTOR.valid && DESCRIPTOR.data.maturity === 'prototype' && !(EXPLICIT.has('makes_external_claims') && cfg.makes_external_claims === true)) {
    CLAIMS_ACTIVE = false
    CLAIMS_REASON = "maturity=prototype — CLAIM activates at 'claimed' (or set makes_external_claims:true)"
  }

  // active profiles: core always; service auto-on for services; others opt-in
  const ACTIVE = new Set(['core'])
  if (cfg.project_type === 'service') ACTIVE.add('service')
  for (const p of (cfg.profiles || [])) ACTIVE.add(p)

  // The unified ledger (M4b, sole path since M7b): kind=sign-off judgments satisfy
  // manual rules by subject. ONE loader and ONE selection rule (jdg.mjs) —
  // schema-valid records only, so a malformed review_by can never read as
  // signed-forever while `jdg check` calls the same file INVALID. The legacy
  // signoff.json dual-read retired with M7's contraction (MIGRATION.md re-mints
  // surviving entries as records). Expiry is judged at evaluation time.
  const JDGS = selectSignoffs(loadJudgments(repo.REPO).records)

  return { cfg, DEFAULTS, EXPLICIT, CLAIMS_ACTIVE, CLAIMS_REASON, ACTIVE, JDGS, DESCRIPTOR }
}
