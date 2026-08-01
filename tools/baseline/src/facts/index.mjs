// gatherFacts — resolve all three planes into ONE plain snapshot. This is where the I/O
// happens (git + the forge queries, incl. resolving the state of every issue a next: or a
// PR "closes #N" references); join and derive are then PURE functions of the snapshot, so
// they replay deterministically from committed forge fixtures.
import { treeFacts } from './tree.mjs'
import { gitFacts, SESSION_BASES, extractNext, laneRefsGit, laneOwner, LANES_PRIV } from './git.mjs'
import { makeForge } from './forge.mjs'
import { globToRe, issueOf, TRAILER_AGENT, nowUTC, refs, closes } from '../util.mjs'
import { DEFAULT_LEASE_TTL, parseTtlMs, deriveLanes } from '../derive/lanes.mjs'
import { run, probeForge } from '../probe.mjs'

// refs/closes moved to util.mjs (boundary-guarded, one home) so derive/* can read them
// without importing this I/O layer; re-exported here for existing importers.
export { refs, closes }

// The raw GraphQL refs() envelope -> plain lane facts. Ref.name arrives RELATIVE to the
// query's refPrefix (verified live 2026-07-14: prefix refs/heads/v2/ answers names like
// 'm5a-lane-claim') — the full ref is dir + name, then filtered by the one-star namespace
// glob. No second spelling is guessed: an ambiguous fallback could misattribute a nested
// ref (lane/lane/7) to its parent name. Replay fixtures therefore carry API-shaped
// (relative) names. Freshness inputs: the tip's committedDate and the NEWEST updatedAt
// across associated PRs (any PR activity is real activity — erring toward LIVE); the
// displayed pr is the open one when there is one.
function normalizeLaneRefs(raw, namespace) {
  const refsNode = raw?.data?.repository?.refs
  if (!Array.isArray(refsNode?.nodes)) return null
  const dir = String(namespace).slice(0, String(namespace).lastIndexOf('/', String(namespace).indexOf('*')) + 1)
  const re = globToRe(namespace)
  const lanes = []
  for (const n of refsNode.nodes) {
    const ref = dir + String(n?.name ?? '')
    if (!re.test(ref) || !n?.target) continue
    const t = n.target
    const prs = Array.isArray(t.associatedPullRequests?.nodes) ? t.associatedPullRequests.nodes.filter(Boolean) : []
    const prUpdatedAt = prs.map(p => p.updatedAt).filter(Boolean).sort().at(-1) ?? null
    const open = prs.find(p => String(p.state).toUpperCase() === 'OPEN') ?? null
    // the LAST trailer-shaped line wins, mirroring git's trailer semantics — the trailer
    // block is the message's final paragraph, so a body line quoting the key (a squash
    // body concatenating old messages) must not shadow it; laneOwner reads the same way
    const agent = ([...String(t.message || '').matchAll(new RegExp(`^${TRAILER_AGENT}:[ \\t]*(.+)$`, 'gm'))].at(-1)?.[1] || '').trim() || null
    lanes.push({
      ref, tip: t.oid ?? null, committedDate: t.committedDate ?? null, prUpdatedAt,
      pr: open ? { number: open.number, title: open.title ?? null, draft: !!open.isDraft, updatedAt: open.updatedAt ?? null } : null,
      prPageTruncated: !!t.associatedPullRequests?.pageInfo?.hasNextPage,
      agent, agentSource: agent ? 'tip-trailer' : null, source: 'forge',
    })
  }
  return { lanes, truncated: !!refsNode.pageInfo?.hasNextPage }
}

// ONE lane-fact gathering for every consumer (orient's view and reclaim's gate read the
// same answer or the tool argues with itself): forge query first (posture-gated inside
// makeForge), git plane as fallback — and as the multi-lane-local posture's normal mode.
// A worked lane's tip no longer carries the claim trailer, so missing owners are
// enriched from git objects (one glob fetch for all lanes, newest-trailer walk each).
// enrich=false (check's world): skip the owner-enrichment git fetch entirely — no check
// rule reads .agent, so the fetch is dead weight AND a stall risk (its 60s timeout hangs
// a check run on a black-holed origin for facts nothing consumes). orient/reclaim pass
// enrich=true (they show/record the agent).
export function gatherLaneFacts(repo, forge, namespace, { enrich = true, defaultBranch = null } = {}) {
  if (!namespace) return { lanes: [], source: null, reason: 'no lanes.namespace declared', truncated: false }
  const viaForge = normalizeLaneRefs(forge.laneRefs(namespace), namespace)
  let got = viaForge ? { ...viaForge, source: 'forge', reason: null } : null
  if (!got) {
    const viaGit = laneRefsGit(repo.REPO, namespace)
    const why = forge.source === 'replay' ? 'no lane-refs replay fixture' : (forge.reason || 'forge lane query failed')
    got = viaGit
      ? { ...viaGit, source: 'git', reason: `${why} — git plane answered${viaGit.truncated ? ' (lane list capped)' : ''}` }
      : { lanes: [], source: null, reason: `${why}; origin unreachable (ls-remote failed)`, truncated: false }
  }
  // Owner enrichment (a worked lane's tip no longer carries the claim trailer) is a LIVE
  // git fetch — forbidden under replay, where facts must come from fixtures alone
  // (forge.mjs's contract: "read fixtures, no network, fully deterministic"). Fixture
  // authors control agents via the tip message.
  if (enrich && got.lanes.some(l => !l.agent) && got.source === 'forge') {
    if (forge.source === 'replay') {
      got.reason = got.reason ?? 'agent enrichment skipped (forge replay — no live fetches)'
    } else {
      const pat = 'refs/heads/' + namespace
      if (run('git', ['-C', repo.REPO, 'fetch', 'origin', `+${pat}:${LANES_PRIV}${namespace}`], { timeout: 60000 }) !== null) {
        for (const l of got.lanes) {
          if (l.agent) continue
          l.agent = laneOwner(repo.REPO, LANES_PRIV + l.ref, issueOf(namespace, l.ref))
          if (l.agent) l.agentSource = 'history-trailer'
        }
      }
    }
  }
  // M7a: the merged-lane fact — a lane whose tip is already an ANCESTOR of the
  // default branch is finished work, not a standing state. Derives COMPLETED
  // downstream, exempting it from DIV-01/lease noise (the live hostage the
  // promotion panel observed: a merged lane's closed anchor is agreement, not
  // divergence). Provable-only: an unknown tip or unresolvable base derives
  // merged:false — not-exempt is the honest default, never a guess. One bounded
  // git spawn per lane (the lane list is already capped at the forge page).
  if (defaultBranch && got.lanes.length) {
    const base = ['origin/' + defaultBranch, defaultBranch].find(r => run('git', ['-C', repo.REPO, 'rev-parse', '--verify', '-q', r + '^{commit}']) !== null) || null
    for (const l of got.lanes) {
      l.merged = !!(base && l.tip && run('git', ['-C', repo.REPO, 'merge-base', '--is-ancestor', l.tip, base]) !== null)
    }
  }
  return got
}

// The LAZY lane-world for `check` (M5c — the plumbing the FLOW/DIV rules evaluate
// through): probe + forge + lane gathering + lease derivation, computed ONCE on first
// demand and only then — a single-lane repo, an off-posture run, or a rule set with
// every lane rule gated off must never pay a gh spawn for it. Exit-stable offline:
// everything degrades to labeled reasons the evaluators turn into SKIPs; nothing throws.
// The SAME gathering + derivation orient and reclaim use — one answer, three surfaces.
export function makeLaneWorld(repo, descriptor, { forgeClosed = null, probe = undefined } = {}) {
  let world = null
  return () => {
    if (world) return world
    const posture = descriptor?.valid ? descriptor.data?.workflow : null
    // no probe under replay (its 3 gh spawns are discarded — forge.mjs forces available;
    // the replay contract is no-network), under the forge-closed posture, or under an
    // explicit closure (M6a's JDG-only admission path — the run PROMISES no forge reads).
    // A caller that already probed (reconcile) threads its result — one probe per run.
    const pf = (forgeClosed || posture === 'multi-lane-local' || process.env.BASELINE_FORGE_REPLAY) ? null : (probe !== undefined ? probe : probeForge(repo))
    // thread the PROBE's specific cause into the forge, so a check SKIP names "gh not
    // installed" / "gh not authenticated" / "no forge repo resolves here" — not the
    // generic "forge unreachable" that would shadow it (orient.mjs's own anti-pattern)
    const forge = makeForge(repo, { available: !!pf?.available, nwo: pf?.repo || null, posture, probeReason: pf?.reason || null, closedReason: forgeClosed })
    const ns = descriptor?.valid ? descriptor.data?.lanes?.namespace : null
    const laneFacts = gatherLaneFacts(repo, forge, ns, { enrich: false, defaultBranch: descriptor?.valid ? descriptor.data?.ground_truth_boundary?.default_branch : null })
    const ttl = (descriptor?.valid ? descriptor.data?.lanes?.lease_ttl : null) ?? DEFAULT_LEASE_TTL
    const now = (nowUTC() ?? new Date()).toISOString()
    // issue states for every lane anchor (DIV-01's input), resolved once, memoized in q()
    const issueStates = {}
    const issueState = n => {
      if (n == null) return 'unknown'
      if (!(n in issueStates)) {
        const it = forge.issue(n)
        issueStates[n] = it ? { state: String(it.state || '').toLowerCase() || 'unknown', title: it.title ?? null } : { state: 'unknown', title: null }
      }
      return issueStates[n].state
    }
    const lanes = ns ? (() => {
      for (const l of laneFacts.lanes) { const n = issueOf(ns, l.ref); if (n != null) issueState(n) }
      return deriveLanes({ lanes: laneFacts.lanes, ttlMs: parseTtlMs(ttl) ?? parseTtlMs(DEFAULT_LEASE_TTL), now, issueStates, namespace: ns })
    })() : []
    world = {
      posture, forge, ns, ttl, now,
      families: (descriptor?.valid ? descriptor.data?.lanes?.families : null) ?? [],
      lanes, source: laneFacts.source, reason: laneFacts.reason,
      issueState, issueStates,
      prsOpen: () => forge.prsOpen(),
      prsOpenOrNull: () => forge.prsOpenOrNull(), // null when the query FAILED (vs [] when closed)
    }
    return world
  }
}

export function gatherFacts(repo, { descriptor, capability }) {
  const tree = treeFacts(repo, descriptor)
  const git = gitFacts(repo)
  // the descriptor's workflow posture rides into makeForge: multi-lane-local CLOSES the
  // forge for the whole gather (CF5) — orient's sections then carry the posture label
  // instead of faking unreachability, exactly like claim (one closure home, M5a)
  const posture = descriptor?.valid ? descriptor.data?.workflow : null
  const forge = makeForge(repo, { available: capability.forge.available, nwo: capability.forge.repo, posture })

  const issues = forge.issuesOpen()
  const openNums = new Set(issues.map(i => i.number))
  const prs = forge.prsOpen().map(pr => {
    const log = SESSION_BASES.reduce((acc, base) => acc || forge.branchLog(base, pr.headRefName), null)
    return { number: pr.number, title: pr.title, branch: pr.headRefName, draft: !!pr.isDraft, updatedAt: pr.updatedAt, next: log?.raw ? extractNext(log.raw) : null, hasLog: !!log, closes: closes(pr.body) }
  })

  // Resolve the state of every referenced issue we can't already see as open (for divergence
  // + join integrity). One forge call per distinct number; memoized, and replayed in tests.
  const referenced = new Set()
  for (const n of refs(git.thisLaneLog?.next)) if (!openNums.has(n)) referenced.add(n)
  for (const pr of prs) { for (const n of refs(pr.next)) if (!openNums.has(n)) referenced.add(n); for (const n of pr.closes) if (!openNums.has(n)) referenced.add(n) }
  // lane refs + lease inputs (M5b) — gathered only when the descriptor declares lanes;
  // resolve every lane anchor's issue state too (a closed anchor is DIV-01's signal)
  const ns = descriptor?.valid ? descriptor.data?.lanes?.namespace : null
  const laneFacts = gatherLaneFacts(repo, forge, ns, { defaultBranch: descriptor?.valid ? descriptor.data?.ground_truth_boundary?.default_branch : null })
  for (const l of laneFacts.lanes) {
    const n = issueOf(ns, l.ref)
    if (n != null && !openNums.has(n)) referenced.add(n)
  }

  const issueStates = {}
  // a stateless answer normalizes to 'unknown' — every layer reading this map (divergence
  // scan, anchor labels) treats '' and 'unknown' differently, so only one may exist
  for (const n of referenced) { const it = forge.issue(n); issueStates[n] = it ? { state: String(it.state || '').toLowerCase() || 'unknown', title: it.title } : { state: 'unknown', title: null } }
  for (const i of issues) issueStates[i.number] = { state: 'open', title: i.title }

  const ttl = (descriptor?.valid ? descriptor.data?.lanes?.lease_ttl : null) ?? DEFAULT_LEASE_TTL
  const lanesMeta = ns ? { namespace: ns, ttl, ttlMs: parseTtlMs(ttl) ?? parseTtlMs(DEFAULT_LEASE_TTL), source: laneFacts.source, reason: laneFacts.reason, truncated: laneFacts.truncated } : null

  // BASELINE_LOG_NOW rides in — the one clock, so lease derivation time-travels with the
  // record tooling; an UNPARSEABLE override falls back to the wall clock LABELED (the CLIs
  // refuse it as usage, but orient never hard-refuses — FS9 — so it degrades, named)
  const nowD = nowUTC()
  return {
    source: forge.source, forgeAvailable: forge.available, forgeReason: forge.reason,
    now: (nowD ?? new Date()).toISOString(),
    nowFallback: nowD ? null : 'BASELINE_LOG_NOW is unparseable — ages derive from the wall clock',
    tree, git, prs, issues, openIssueNumbers: [...openNums], issueStates,
    lanes: laneFacts.lanes, lanesMeta,
  }
}
