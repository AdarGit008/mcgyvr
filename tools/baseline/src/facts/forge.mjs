// Forge facts (typed, provenance-carrying), fetched via `gh` and memoized per run. Three modes:
//   live    — call gh, write-through the advisory cache
//   record  — BASELINE_FORGE_RECORD=<dir>: also persist each response as a committed fixture
//   replay  — BASELINE_FORGE_REPLAY=<dir>: read fixtures, no network, fully deterministic
// so downstream lane/admit tests (and this slice's own) replay a fixed forge without a network.
// Never throws: an absent/failed query -> null (list queries coalesce to []), and callers degrade.
// GraphQL batching is deferred until fleet-scale rate pressure is real (M5) — for a single run
// these gh queries return identical facts.
//
// M6b adds the MUTATION channel (reconcile's write surface — the ONLY writes the tool
// ever sends to a forge, and never to the repo/main):
//   live    — exec gh; under RECORD also persist each {plan, result} as mut-NNN.json
//   replay  — no network: assert this run's Nth plan deepEqs the recorded Nth plan —
//             a replayed test proves the exact ordered writes, not just the reads
//   dry-run — collect the plan, execute nothing (the caller prints it)
//   closed  — a posture-/JDG-closed or unreachable forge cannot write: mutate()
//             refuses with the same one-home reason the read path carries
import fs from 'node:fs'
import path from 'node:path'
import { gh, ghJson } from '../probe.mjs'
import { deepEq, normalizeVolatile } from '../util.mjs'
import { cacheWrite } from '../cache.mjs'

export function makeForge(repo, { available = false, nwo = null, posture = null, probeReason = null, closedReason = null, mutations = 'live' } = {}) {
  // CF5: a multi-lane-local posture CLOSES the forge — and replay must not reopen it,
  // or fixtures would derive from consultations the posture promises never happen.
  // One home for the closure + its reason string; every surface (claim now, leases/
  // rules at M5b/M5c) inherits the same honest label instead of hand-rolling the gate.
  // M6a: closedReason is the same one-home closure for NON-posture closures — the
  // JDG-only admission path promises the run depends on no forge plane, so replay
  // must not reopen it either.
  const CLOSED = closedReason != null || posture === 'multi-lane-local'
  const REPLAY = process.env.BASELINE_FORGE_REPLAY || null
  const RECORD = process.env.BASELINE_FORGE_RECORD || null
  const memo = new Map()
  const isAvail = () => CLOSED ? false : (REPLAY ? true : !!available)

  const readFixture = (key) => { try { return JSON.parse(fs.readFileSync(path.join(REPLAY, key + '.json'), 'utf8')) } catch { return undefined } }
  const writeFixture = (key, val) => { try { fs.mkdirSync(RECORD, { recursive: true }); fs.writeFileSync(path.join(RECORD, key + '.json'), JSON.stringify(val, null, 2) + '\n') } catch {} }

  // Memoized fetch by stable key. Replay short-circuits gh (and the cache) entirely.
  function q(key, ghArgs, { raw = false, maxBuffer } = {}) {
    if (memo.has(key)) return memo.get(key)
    let val
    if (REPLAY) {
      const f = readFixture(key)
      val = f === undefined ? null : (raw && f && typeof f === 'object' ? (f.raw ?? null) : f)
    } else if (!isAvail()) {
      val = null
    } else {
      val = raw ? gh(ghArgs, { cwd: repo.REPO, maxBuffer }) : ghJson(ghArgs, { cwd: repo.REPO, maxBuffer })
      if (val != null) { if (RECORD) writeFixture(key, raw ? { raw: val } : val); cacheWrite(repo, key, val) }
    }
    memo.set(key, val)
    return val
  }

  const safeKey = (s) => String(s).replace(/[^A-Za-z0-9._-]/g, '_')

  // ---- the mutation channel (M6b) ----
  // Plans are plain JSON ({ action, key, issue?, title? }); recordings carry the
  // plan AND the gh argv with volatile content collapsed (normalizeVolatile — shas,
  // ages, dates), so replay asserts both INTENT and INVOCATION while fixtures stay
  // stable across re-materialized repos. Sequence-numbered: replay asserts the Nth
  // live plan deepEqs the Nth recorded plan — order is part of the promise, so
  // callers must plan in a deterministic order (reconcile sorts by dedup key).
  // A replay mismatch is a harness-contract violation, never a relievable outage.
  // Seq discipline: a failed/mismatched mutation still consumes its seq (its paired
  // follow-up is skipped), so later seqs shift against recordings and cascade as
  // mismatches — fail-CLOSED by construction (exit 1, failed[0].reason names the
  // root), and a partially-failed RECORD run is honestly unreplayable.
  let mutSeq = 0
  const mutLog = []
  const readMutFixture = (seq) => { try { return JSON.parse(fs.readFileSync(path.join(REPLAY, `mut-${String(seq).padStart(3, '0')}.json`), 'utf8')) } catch { return undefined } }
  // repo identity is AMBIENT, not intent: replay runs have no probe (nwo null), so
  // the recorded argv's real owner/repo could never match — collapse it on both
  // sides and the assertion keeps endpoint shape + payloads, which ARE the intent.
  const normArg = (a) => normalizeVolatile(String(a)).replace(/\brepos\/[^/\s]+\/[^/\s]+/g, 'repos/<nwo>')
  function mutate(plan, ghArgs) {
    const seq = mutSeq++
    const normArgs = ghArgs.map(normArg)
    if (mutations === 'dry') { mutLog.push({ seq, plan, mode: 'dry', ok: true }); return { ok: true, dry: true, result: null } }
    if (CLOSED) { mutLog.push({ seq, plan, mode: 'closed', ok: false }); return { ok: false, reason: closedReason || 'forge not consulted (multi-lane-local posture)' } }
    if (REPLAY) {
      const rec = readMutFixture(seq)
      if (rec === undefined) { mutLog.push({ seq, plan, mode: 'replay', ok: false }); return { ok: false, replayMismatch: true, reason: `mutation ${seq} has no recording (mut-${String(seq).padStart(3, '0')}.json) — the replayed run plans a write the recording never made` } }
      if (!deepEq(rec.plan, plan)) { mutLog.push({ seq, plan, mode: 'replay', ok: false }); return { ok: false, replayMismatch: true, reason: `mutation ${seq} diverges from its recording — planned ${JSON.stringify(plan)}, recorded ${JSON.stringify(rec.plan)}` } }
      if (rec.ghArgs && !deepEq(rec.ghArgs, normArgs)) { mutLog.push({ seq, plan, mode: 'replay', ok: false }); return { ok: false, replayMismatch: true, reason: `mutation ${seq}: plan matches but the INVOCATION diverges — argv ${JSON.stringify(normArgs)}, recorded ${JSON.stringify(rec.ghArgs)}` } }
      mutLog.push({ seq, plan, mode: 'replay', ok: true })
      return { ok: true, result: rec.result ?? null }
    }
    if (!isAvail()) { mutLog.push({ seq, plan, mode: 'closed', ok: false }); return { ok: false, reason: probeReason || 'forge unreachable' } }
    const result = ghJson(ghArgs, { cwd: repo.REPO })
    const ok = result !== null
    mutLog.push({ seq, plan, mode: 'live', ok })
    if (ok && RECORD) { try { fs.mkdirSync(RECORD, { recursive: true }); fs.writeFileSync(path.join(RECORD, `mut-${String(mutSeq - 1).padStart(3, '0')}.json`), JSON.stringify({ plan, ghArgs: normArgs, result }, null, 2) + '\n') } catch {} }
    return ok ? { ok: true, result } : { ok: false, reason: 'forge write failed (gh exited nonzero — token lacks write, rate limit, or network)' }
  }

  return {
    available: isAvail(),
    source: CLOSED ? 'posture' : REPLAY ? 'replay' : 'forge',
    // the probe's specific cause wins over the generic label when the caller threaded one
    reason: isAvail() ? null : CLOSED ? (closedReason || 'forge not consulted (multi-lane-local posture)') : (probeReason || 'forge unreachable'),
    prsOpen() { return isAvail() ? (q('prs-open', ['pr', 'list', '--state', 'open', '--json', 'number,title,headRefName,isDraft,updatedAt,body', '--limit', '50']) || []) : [] },
    // null-honest variant: a null (the gh query FAILED after the probe said available)
    // must not coalesce to [] and let a rule assert "no open PRs" as fact — the caller
    // SKIPs on null. [] only when the forge is genuinely closed/unreachable up front.
    prsOpenOrNull() { return isAvail() ? q('prs-open', ['pr', 'list', '--state', 'open', '--json', 'number,title,headRefName,isDraft,updatedAt,body', '--limit', '50']) : [] },
    issuesOpen() { return isAvail() ? (q('issues-open', ['issue', 'list', '--state', 'open', '--json', 'number,title,labels,milestone,updatedAt', '--limit', '200']) || []) : [] },
    issue(n) { return isAvail() ? q(`issue-${safeKey(n)}`, ['issue', 'view', String(n), '--json', 'number,state,title']) : null },
    // M5b: every lane tip's committedDate + associated-PR updatedAt in ONE GraphQL refs()
    // query (FS10 as amended — pushedDate is gone from the schema; batching beyond this
    // stays deferred until F2's fleet-scale trigger fires). Returns the RAW GraphQL
    // envelope (that is what record/replay persists); facts/index normalizes downstream.
    // refPrefix must be a '/'-terminated path, so the namespace's directory part goes in
    // the query and the one-star glob is re-applied client-side by the normalizer.
    laneRefs(namespace) {
      if (!isAvail() || !namespace) return null
      const dir = String(namespace).slice(0, String(namespace).lastIndexOf('/', String(namespace).indexOf('*')) + 1)
      const prefix = 'refs/heads/' + dir
      const QUERY = 'query($owner:String!,$name:String!,$prefix:String!){repository(owner:$owner,name:$name){refs(refPrefix:$prefix,first:100){pageInfo{hasNextPage}nodes{name target{... on Commit{oid committedDate message associatedPullRequests(first:20){pageInfo{hasNextPage}nodes{number state isDraft title updatedAt}}}}}}}}'
      const [owner, name] = String(nwo || '/').split('/')
      return q(`lane-refs-${safeKey(prefix)}`, ['api', 'graphql', '-f', `query=${QUERY}`, '-f', `owner=${owner}`, '-f', `name=${name}`, '-f', `prefix=${prefix}`])
    },
    // ---- M6b reads ----
    // The GOV readable-surface ladder (ruled): rules-for-branch is a PLAIN read (no
    // admin), the branch `protected` flag is plain, the classic /protection endpoint
    // needs admin and is consulted only when the caller opted in. run() nulls every
    // failure identically, so the 403-vs-down distinction is derived honestly by the
    // caller: rules null while branchMeta answers = unreadable WITH THIS TOKEN;
    // both null = the forge plane itself degraded (probe reason wins).
    branchRules(branch) { return isAvail() && branch ? q(`branch-rules-${safeKey(branch)}`, ['api', `repos/${nwo}/rules/branches/${encodeURIComponent(branch)}`]) : null },
    branchMeta(branch) { return isAvail() && branch ? q(`branch-meta-${safeKey(branch)}`, ['api', `repos/${nwo}/branches/${encodeURIComponent(branch)}`]) : null },
    branchProtection(branch) { return isAvail() && branch ? q(`branch-protection-${safeKey(branch)}`, ['api', `repos/${nwo}/branches/${encodeURIComponent(branch)}/protection`]) : null },
    // Check-run conclusions at a sha — merged-while-red's input now, the digest's
    // (name, conclusion, head_sha) tuple source at M6c. ONE page, per_page=100 —
    // a red admit beyond page 1 is a silent miss (detection understated, never a
    // false positive); pagination joins the M6c digest work if real heads exceed it.
    checkRuns(sha) { return isAvail() && sha ? q(`check-runs-${safeKey(sha)}`, ['api', `repos/${nwo}/commits/${sha}/check-runs?per_page=100`]) : null },
    // Recently-merged PRs into a base — merged-while-red's sweep window (a squash
    // merge's red admit lives on the PR HEAD sha, which never lands on the base, so
    // the tip alone can literally never show it). Bounded 20 newest-merged; the
    // caller labels the window.
    prsMerged(base) { return isAvail() ? q(`prs-merged-${safeKey(base || 'all')}`, ['pr', 'list', '--state', 'merged', '--limit', '20', ...(base ? ['--base', base] : []), '--json', 'number,title,headRefOid,mergeCommit,mergedAt']) : null },
    // Every LABELED issue in every state, bodies included — the dedup lifecycle's ONE
    // search surface (markers parse client-side; the search API's indexing lag would
    // make file→close cycles flap; the label scopes the scan so a busy tracker's
    // unrelated issues never crowd the window). Bounded at 500 newest; the caller
    // labels truncation and suppresses creates under it. Bodies are big: an explicit
    // maxBuffer keeps run()'s 1MB default from silently nulling the whole listing.
    issuesLabeled(label) { return isAvail() ? q(`issues-labeled-${safeKey(label)}`, ['issue', 'list', '--state', 'all', '--label', label, '--limit', '500', '--json', 'number,state,title,body,updatedAt'], { maxBuffer: 64 * 1024 * 1024 }) : null },
    // M7c: OPS-07's ONE workflow-state query — GET /repos/:nwo/actions/workflows/:file
    // returns {state}: 'active' or the disabled_* family (disabled_inactivity is
    // GitHub's 60-day auto-disable, the rule's named death mode). Keyed by the
    // workflow file's basename; null on any failure (the caller SKIPs, never guesses).
    workflowState(file) { return isAvail() && file ? q(`workflow-state-${safeKey(file)}`, ['api', `repos/${nwo}/actions/workflows/${encodeURIComponent(file)}`]) : null },
    mutate,
    mutationLog: () => mutLog,
    // Newest session log on a branch, read from origin at that ref via the contents API.
    branchLog(base, branch) {
      if (!isAvail()) return null
      const listing = q(`contents-${safeKey(base)}-${safeKey(branch)}`, ['api', `repos/${nwo}/contents/${base}/${branch}?ref=${branch}`])
      if (!Array.isArray(listing)) return null
      const files = listing.filter(e => e.type === 'file' && String(e.name).endsWith('.md')).map(e => e.name).sort()
      if (!files.length) return null
      const raw = q(`rawlog-${safeKey(branch)}-${safeKey(files.at(-1))}`, ['api', `repos/${nwo}/contents/${base}/${branch}/${files.at(-1)}?ref=${branch}`, '-H', 'Accept: application/vnd.github.raw'], { raw: true })
      return { file: files.at(-1), raw: raw || null }
    },
  }
}
