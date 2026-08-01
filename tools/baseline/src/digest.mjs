// inputs_digest (M6c) — the pure provenance function, as ruled: the digest names
// exactly what an admission verdict was derived FROM, so a later reader (or M7's
// binding) can tell two admissions apart without trusting prose. Inputs, per the
// ruling: head SHA · target SHA · the descriptor's blob OID at the target (the
// content-addressed "descriptor hash" — gitBlobAt; over-invalidates safely, never
// under-invalidates) · rules version · check-run (name, conclusion, head_sha)
// tuples (F8's fold: ONE query's recording) · anchored-issue state.
//
// Canonicalization is the whole contract:
//   - fixed field order (object key order never leaks into the hash)
//   - check tuples FULL-tuple sorted — API page order is not identity
//   - ABSENT is a VALUE, not a hole: a closed/unreachable forge digests as
//     'not-consulted', an anchorless branch as 'none' — two runs that consulted
//     different planes MUST digest differently, and a hole would let them collide.
// Pure and clock-free by construction; stability is unit-tested (tuple
// permutation, absent-vs-null, empty-vs-missing).
import crypto from 'node:crypto'

// Tuple-join separator for the sort key: NUL cannot appear in the field strings,
// so concat-equal-but-differently-split tuples (['a b','c'] vs ['a','b c']) never
// collide — a space join would. Escape form on purpose: a raw NUL byte would make
// this file binary to git and the pure provenance function unreviewable in a diff.
const SEP = '\u0000'

export function inputsDigest({ head, target, descriptorOid, rulesVersion, checkRuns, anchor }) {
  const canon = {
    head: head ?? null,
    target: target ?? null,
    descriptor_oid: descriptorOid ?? null,
    rules_version: rulesVersion ?? null,
    // FULL-tuple sort: GitHub re-runs mint same-name runs at one sha, so a
    // name-only sort would leave API page order inside the digest. An in-progress
    // run's null conclusion serializes as '' — a value, distinct and stable.
    check_runs: (checkRuns === null || checkRuns === undefined) ? 'not-consulted'
      : [...checkRuns]
        .map(r => [String(r.name ?? ''), String(r.conclusion ?? ''), String(r.head_sha ?? '')])
        .sort((a, b) => { const A = a.join(SEP), B = b.join(SEP); return A < B ? -1 : A > B ? 1 : 0 }),
    anchor: (anchor === null || anchor === undefined) ? 'none' : { issue: anchor.issue ?? null, state: String(anchor.state ?? 'unknown') },
  }
  return crypto.createHash('sha256').update(JSON.stringify(canon)).digest('hex').slice(0, 12)
}

// Provenance is REFUSAL-INERT by contract: its assembly never contributes to
// admit's refusals, results, or summary — a lost source digests as
// 'not-consulted', labeled, never refused (the 0-re-pins budget rests on this).
// The JSON field mirrors the LINE's own fields only (digest, head, target,
// descriptor_oid, rules_version, checks, anchor) — the raw tuple echo's consumer
// was V3's cut ceremony; nothing reads it now, so nothing ships it.
export function provenanceJson({ digest, head, target, descriptorOid, rulesVersion, checkRuns, anchor }) {
  return {
    digest, head, target,
    descriptor_oid: descriptorOid ?? null,
    rules_version: rulesVersion ?? null,
    checks: (checkRuns === null || checkRuns === undefined) ? 'not-consulted' : checkRuns.length,
    anchor: (anchor === null || anchor === undefined) ? null : { issue: anchor.issue ?? null, state: String(anchor.state ?? 'unknown') },
  }
}

// The one human spelling of the provenance line (admit prints it; tests pin the
// shape). Degradations ride the line honestly — 'not consulted' and 'none' are
// words, never omissions.
export function provenanceLine({ digest, head, target, descriptorOid, rulesVersion, checkRuns, anchor }) {
  const checks = (checkRuns === null || checkRuns === undefined) ? 'checks not consulted' : `${checkRuns.length} check run(s)`
  const anch = (anchor === null || anchor === undefined) ? 'anchor none' : `anchor #${anchor.issue} ${anchor.state}`
  return `provenance: inputs_digest ${digest} · head ${String(head).slice(0, 7)} → target ${String(target).slice(0, 7)} · descriptor ${descriptorOid ? String(descriptorOid).slice(0, 7) : 'absent'} · rules ${rulesVersion} · ${checks} · ${anch}`
}
