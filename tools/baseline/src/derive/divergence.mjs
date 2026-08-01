// derive/divergence — PURE: (plain facts) -> the cross-tier contradictions a stateless
// worker must resolve before trusting anything else (C36). Extracted from derive/status
// at M5c so the DIV RULES and orient's headline read ONE derivation — a rule that fires
// where orient stays quiet (or vice versa) would be the tool arguing with itself.
//
// Three codes (the ADR-0009 prototype's check-session-log cases, generalized):
//   DIV-01  issue-closed-lane-active — a claimed lane whose anchor issue is closed
//   DIV-02  next:-points-at-closed  — a recorded next step naming a closed issue
//   DIV-03  done-with-nothing-merged — an open PR "closes #N" where #N is already closed
//
// Certainty is deterministic (the forge SAID the issue is closed); blocker since
// M7a — the engine tag stays DIVERGED and the counting seams fail the run. An 'unknown' issue state is
// NEVER divergence — unresolvable is surfaced by the join layer, not guessed here.
// refs comes from util (pure) so this derive module reads no I/O layer.
import { refs } from '../util.mjs'

// The ONE definition of "closed" — orient's headline (this module), the DIV rules
// (evaluators), and lanes' anchor label all import THIS, so a change to what closed
// means (e.g. a future 'not_planned' handling) can never update one surface and not
// the others. That single-source guarantee is the whole point of the extraction.
export const isClosed = s => !!s && s !== 'open' && s !== 'unknown'

// -> [{ code, where, issue, state, text }] — plain items; renderers make strings.
export function deriveDivergence({ lanes = [], prs = [], issueStates = {}, thisLane = null }) {
  const stateOf = n => issueStates[n]?.state
  const titleOf = n => issueStates[n]?.title || ''
  const items = []

  // DIV-01: a lane still claimed/active whose anchor issue is closed — the work
  // surface says "in progress", the issue tracker says "done"; one of them lies.
  // A COMPLETED lane (tip merged into the default branch, M7a) is EXEMPT: its
  // closed anchor is agreement with the tracker — finished work, not contradiction
  // (the promotion's live-hostage guard; the lane line still says "prune").
  for (const l of lanes) {
    if (l.state === 'COMPLETED') continue
    if (l.anchor && isClosed(l.anchor.state)) {
      items.push({ code: 'DIV-01', where: l.ref, issue: l.anchor.issue, state: l.anchor.state, text: `lane ${l.ref} is claimed but its anchor #${l.anchor.issue} is ${l.anchor.state} — "${titleOf(l.anchor.issue)}"` })
    }
  }

  // DIV-02: a next: pointer at an issue that is no longer open (this lane's newest
  // record, and each PR's branch record).
  const scanNext = (where, nextStr) => {
    for (const n of refs(nextStr)) if (isClosed(stateOf(n))) items.push({ code: 'DIV-02', where, issue: n, state: stateOf(n), text: `${where}: next: points at #${n} (${stateOf(n)}) — "${titleOf(n)}"` })
  }
  if (thisLane?.next) scanNext(`this lane (${thisLane.branch})`, thisLane.next)
  for (const pr of prs) if (pr.next) scanNext(`#${pr.number} ${pr.branch}`, pr.next)

  // DIV-03: a live PR closes an already-closed issue — done-with-nothing-merged.
  for (const pr of prs) for (const n of (pr.closes || [])) {
    if (isClosed(stateOf(n))) items.push({ code: 'DIV-03', where: `#${pr.number} ${pr.branch}`, issue: n, state: stateOf(n), text: `#${pr.number} ${pr.branch}: closes #${n}, already ${stateOf(n)} — "${titleOf(n)}"` })
  }
  return items
}
