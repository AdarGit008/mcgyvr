// derive/lanes — a PURE function: (plain lane facts, ttl, now) -> the three-state lease
// view (C31: LIVE | STALE | ABANDONED, nothing stored to go stale). No I/O — inputs are
// plain JSON-able data, which is also the M6 `inputs_digest` seam: the same object that
// derives here can be digested there without a second gathering pass.
//
// Freshness is FS10 as amended (the M5 ruling): GitHub's GraphQL schema no longer carries
// Commit.pushedDate, so freshness = max(tip committedDate, PR updatedAt) — the LATER
// signal wins (erring toward LIVE: a premature ABANDONED invites a premature reclaim,
// the one direction that steals a live lane). Provenance rides the lane as a label; a
// git-plane-only lane says so (committer clock, no PR corroboration — low confidence).
// Clock skew (freshness ahead of now) clamps to age 0, labeled — a skewed clock must
// read as maximally live, never as negative-age weirdness or a premature reclaim.
// A lane with NO resolvable freshness derives state null — surfaced, never guessed;
// reclaim refuses anything but a derived ABANDONED, so an unresolvable lane is not
// reclaimable without a deviation judgment (the --jdg hatch is the ONLY way past it).
import { issueOf } from '../util.mjs'
import { isClosed } from './divergence.mjs'

export const DEFAULT_LEASE_TTL = '7d' // D2: the descriptor default when lanes.lease_ttl is undeclared

// STALE begins at ttl/2 — a PROVISIONAL named constant, deliberately not a descriptor
// knob (M7 revisits on dogfood data; a knob now would fossilize a guess as an interface).
export const STALE_FRACTION = 0.5

// '7d' | '36h' -> milliseconds; null when unparseable — including a zero ttl ('0d' would
// invert the lease semantics into nothing-ever-reclaimable; the schema pattern refuses it
// too, and refusing it HERE means a zero can never ride in through any other door and
// callers fall back to DEFAULT).
export function parseTtlMs(ttl) {
  const m = /^([1-9][0-9]*)([dh])$/.exec(String(ttl ?? ''))
  return m ? +m[1] * (m[2] === 'd' ? 86400000 : 3600000) : null
}

const RANK = { ABANDONED: 0, STALE: 1, LIVE: 3, COMPLETED: 4 } // underived (null) ranks 2: attention-worthy, not reclaimable; COMPLETED sorts last (done is not attention)

// lanes: [{ ref, tip, committedDate, prUpdatedAt, pr, agent, agentSource, source }] — the
// normalized facts (src/facts/*). -> the derived view, ABANDONED/STALE sorted first (the
// reclaimable and the drifting are what a session must see before picking work).
export function deriveLanes({ lanes = [], ttlMs, now, issueStates = {}, namespace = null }) {
  const nowMs = Date.parse(now ?? '')
  const view = lanes.map(l => {
    const labels = []
    const commit = Date.parse(l.committedDate ?? '')
    const pr = Date.parse(l.prUpdatedAt ?? '')
    let freshness = null, basis = null
    if (!isNaN(commit) || !isNaN(pr)) {
      basis = (isNaN(pr) || (!isNaN(commit) && commit >= pr)) ? 'tip-commit' : 'pr-update'
      freshness = new Date(Math.max(isNaN(commit) ? -Infinity : commit, isNaN(pr) ? -Infinity : pr)).toISOString()
    }
    let age_ms = null, state = null
    // M7a: a lane whose tip is ALREADY an ancestor of the default branch is finished
    // work — COMPLETED, exempt from the lease clock and from DIV-01 (its closed
    // anchor is agreement with the tracker, not a contradiction). The fact is
    // provable-only (gathered upstream via git ancestry); absent proof, the lane
    // derives on the normal clock — not-exempt is the honest default.
    if (l.merged) {
      state = 'COMPLETED'
      labels.push('tip merged into the default branch — lane complete; prune the branch (git push origin --delete <ref>)')
    } else if (freshness != null && !isNaN(nowMs) && ttlMs > 0) {
      age_ms = nowMs - Date.parse(freshness)
      if (age_ms < 0) { age_ms = 0; labels.push('clock skew clamped to age 0 (freshness is ahead of now)') }
      state = age_ms < ttlMs * STALE_FRACTION ? 'LIVE' : age_ms < ttlMs ? 'STALE' : 'ABANDONED'
      labels.push(`freshness: ${basis === 'pr-update' ? 'PR activity' : 'tip commit'}${l.source === 'git' ? ' — git plane, committer clock (low confidence)' : ''}`)
      if (l.prPageTruncated) labels.push('PR page truncated at the forge — newer PR activity may exist (freshness can only be understated)')
    } else {
      // name the ACTUAL missing input — "freshness unresolvable" on a lane whose
      // freshness resolved fine (bad ttl/now) would be a mislabel, not a degradation
      labels.push(freshness == null
        ? 'freshness unresolvable — state underived (not reclaimable without a deviation judgment)'
        : `lease inputs unresolvable (${!(ttlMs > 0) ? 'ttl' : 'now'}) — state underived (not reclaimable without a deviation judgment)`)
    }
    const issue = namespace ? issueOf(namespace, l.ref) : null
    if (namespace && issue == null) labels.push('no issue anchor (ref name is not an issue number)')
    // anchor resolution: the lane's issue, and what the forge last said about it — a
    // closed anchor under a live lane is DIV-01's territory (the rule lands at M5c;
    // the derivation lives here so orient and the rule read ONE answer).
    const anchor = issue != null ? { issue, state: issueStates[issue]?.state ?? 'unknown' } : null
    if (anchor && isClosed(anchor.state)) labels.push(`anchor #${issue} is ${anchor.state}`)
    return {
      ref: l.ref, tip: l.tip ?? null, issue, agent: l.agent ?? null, agentSource: l.agentSource ?? null,
      source: l.source ?? null, pr: l.pr ?? null, freshness, basis, age_ms, state, anchor, labels,
    }
  })
  return view.sort((a, b) =>
    ((RANK[a.state] ?? 2) - (RANK[b.state] ?? 2)) || ((b.age_ms ?? 0) - (a.age_ms ?? 0)) || (a.ref < b.ref ? -1 : a.ref > b.ref ? 1 : 0))
}
