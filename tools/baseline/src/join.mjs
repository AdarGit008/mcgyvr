// The join layer (C38): relate work items across planes using ONLY declared keys
// (schema/keys.md). A join that cannot be resolved is a FINDING, never a guess — the anti-NLP
// discipline that keeps derived state honest. Active keys this slice: PR⇄branch (headRefName)
// and PR⇄issue (a "closes #N" reference). Record/session/JDG/CLM keys are declared in
// schema/keys.md but stay inert until M4/M5 create those records.
export function join(facts) {
  const open = new Set(facts.openIssueNumbers)
  const edges = []
  const findings = []
  for (const pr of facts.prs) {
    edges.push({ from: `pr#${pr.number}`, to: `branch:${pr.branch}`, key: 'headRefName' })
    for (const n of pr.closes) {
      const known = open.has(n) || (facts.issueStates[n] && facts.issueStates[n].state !== 'unknown')
      if (known) edges.push({ from: `pr#${pr.number}`, to: `issue#${n}`, key: 'closes' })
      else findings.push({ kind: 'unresolvable-join', key: 'closes', detail: `PR #${pr.number} declares "closes #${n}", but no such issue resolves` })
    }
  }
  return { edges, findings }
}
