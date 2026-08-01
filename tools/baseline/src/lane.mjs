// `baseline lane` — the lane surfaces (M5; claim shipped at M5a, reclaim is the M5b slice).
// The claim primitive (FS2/S3): ATOMIC BRANCH CREATION AT ORIGIN — ref creation inside the
// remote's ref transaction is first-wins, so the race needs no forge CAS, no lock file, and
// no assignment ceremony (issue assignment is informational only). The ref identity is the
// descriptor's lanes.namespace with the issue number substituted — EXACTLY that (M5 panel,
// FS-1): user slugs were cut because two spellings would both push-succeed and mint two
// lanes for one issue; descriptiveness is orient's job. Lane identity = branch name +
// Baseline-Agent trailer (C38: claim machine-generates only descriptor-declared join keys —
// an absent join_keys refuses like an incomplete one, or M5b's join could never read back
// what claim writes).
//
// Checkout-free (M5 panel, DA-6): the claim commit is built with commit-tree against a
// PRIVATE fetched ref and pushed sha:ref — HEAD, worktree, and local branch list are
// untouched until AFTER the push wins, so the loser exits clean with no partial state
// structurally, not via cleanup. FETCH_HEAD is never read: it is one shared file any
// concurrent fetch (IDE autofetch, a sibling agent) rewrites between our fetch and read.
//
// The race is settled honestly in BOTH directions: a ref that exists under this agent's
// own trailer is an idempotent win (a crashed claimer rerunning must not be told it "lost"
// to itself and go double-claim another issue), and a push whose failure report arrives
// after origin applied the ref is recognized by tip==sha as a win, never a fake loss.
//
// RECLAIM (M5b): takeover of a DERIVED-ABANDONED lane only — the state comes from the same
// gathering + derivation orient renders (one answer, or the tool argues with itself). The
// takeover commit is a child of the observed tip carrying the new agent's trailer, pushed
// WITHOUT force: if the lane moved meanwhile the push rejects non-fast-forward and the
// re-ask names the truth (the lane is active — exit 3, never a stolen live lane). A live
// takeover exists only through the ledger: --jdg <id> naming an unexpired deviation for
// this lane (the escape hatch that keeps humans inside the tool instead of around it).
// The dated takeover record is machine-written through the existing `baseline log` writer
// (no human ceremony), and the issue comment is best-effort, posture-gated.
//
// Posture: workflow multi-lane-local (CF5) never consults the forge — makeForge owns the
// closure and its label ("forge not consulted (multi-lane-local posture)"), so replay
// fixtures cannot fake a consultation the posture forbids. Otherwise the forge, when
// reachable, refuses a claim on an issue positively known closed (divergence at birth,
// DIV-01's territory); an unknown or stateless answer proceeds labeled — the push decides.
//   exit: 0 claimed/reclaimed (or already this agent's) · 2 usage/refusal/environment · 3 lost race
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { execFileSync, spawnSync } from 'node:child_process'
import { makeOpt, TRAILER_ISSUE, TRAILER_AGENT, issueOf, escRe, nowUTC } from './util.mjs'
import { liteRepo } from './repo.mjs'
import { loadDescriptor, DESCRIPTOR_FILE } from './descriptor.mjs'
import { probeForge, resolveAgent, run, gh } from './probe.mjs'
import { makeForge } from './facts/forge.mjs'
import { gatherLaneFacts } from './facts/index.mjs'
import { laneOwner } from './facts/git.mjs'
import { deriveLanes, parseTtlMs, DEFAULT_LEASE_TTL } from './derive/lanes.mjs'
import { loadJudgments } from './jdg.mjs'

const LANE_USAGE = `usage: baseline lane claim <issue> [--agent A] [--repo DIR] [--json]
         baseline lane reclaim <issue|ref> [--jdg JDG-ID] [--agent A] [--repo DIR] [--json]`
const VALUE_FLAGS = ['--repo', '--agent', '--jdg']
// private refs for race-free reads: the claim base, the existing-tip peek, the reclaim
// base — pid-suffixed, because a fixed name is one shared cell two concurrent baseline
// processes in the SAME clone would rewrite under each other (the FETCH_HEAD lesson,
// applied to our own refs: a reclaim of lane/9 mid-flight must never re-point the ref a
// reclaim of lane/7 is about to read its tree from)
const BASE_REF = `refs/baseline/claim-base-${process.pid}`
const PEEK_REF = `refs/baseline/claim-peek-${process.pid}`
const RECLAIM_REF = `refs/baseline/reclaim-base-${process.pid}`

export function runLane(argv) {
  if (argv[0] === '--help' || argv[0] === '-h') {
    console.log(`baseline lane — claim and reclaim work lanes (atomic ref transactions at origin)\n  ${LANE_USAGE}\n  exit: 0 claimed/reclaimed (or the lane already stands under this agent's trailer) · 2 usage/refusal/environment · 3 lost race (claim: another agent claimed it · reclaim: the lane moved — it is active)`)
    return 0
  }
  if (argv[0] === 'claim') return runClaim(argv.slice(1))
  if (argv[0] === 'reclaim') return runReclaim(argv.slice(1))
  console.error(`baseline lane: ${argv.length ? `unknown action '${argv[0]}'` : 'which action?'} (actions: claim · reclaim)\n  ${LANE_USAGE}`)
  return 2
}

// ---- shared gates: the descriptor is the only place a lane name may come from (C10),
// ---- and both writers stamp ONLY declared join keys (C38) — one refusal voice ----
function descriptorGates(repo, usage, verb) {
  const d = loadDescriptor(repo)
  if (!d.present) return usage(`no ${DESCRIPTOR_FILE} — lane ${verb} derives the branch from the descriptor's lanes.namespace (declare it: copy a config-presets/*.repo.json posture preset)`)
  if (!d.valid) return usage(`${DESCRIPTOR_FILE} is invalid (${d.errors[0] || 'schema error'}) — ${verb} refuses to guess a namespace from a broken descriptor`)
  const ns = d.data.lanes?.namespace
  if (!ns) return usage(`descriptor declares no lanes.namespace — add e.g. "lanes": { "namespace": "lane/*" }`)
  if ((ns.match(/\*/g) || []).length !== 1) return usage(`lanes.namespace '${ns}' must contain exactly one '*' (the issue number replaces it — one deterministic ref per issue is what makes the claim a race with one winner)`)
  const jk = Array.isArray(d.data.join_keys) ? d.data.join_keys : []
  const missing = [TRAILER_AGENT, TRAILER_ISSUE].filter(k => !jk.includes(k))
  if (missing.length) {
    return usage(`descriptor ${Array.isArray(d.data.join_keys) ? `join_keys omits ${missing.join(' + ')}` : 'declares no join_keys'} — ${verb} stamps exactly those trailers (C38), and undeclared keys could never be joined back. Declare: "join_keys": ["${TRAILER_AGENT}", "${TRAILER_ISSUE}"]`)
  }
  return { d, ns }
}

// ---- shared local landing for a won ref: tracking ref, branch (guarding a pre-existing
// ---- local one), upstream (single-branch-refspec-proof), checkout ----
function landLocal(G, ref, sha, note) {
  // the push doesn't create refs/remotes/origin/<ref> in single-branch clones and a
  // plain fetch wouldn't either (refspec) — we KNOW the sha, so write the tracking
  // ref directly: offline, refspec-proof, and set-upstream then just works
  G('update-ref', `refs/remotes/origin/${ref}`, sha)
  const localTip = G('rev-parse', '--verify', '--quiet', `refs/heads/${ref}`) || null
  let branched = false, checkout = false
  if (localTip === sha) {
    branched = true // rerun after a crash-past-checkout: the local branch IS the claim
    checkout = G('checkout', ref) !== null
  } else if (localTip) {
    // a pre-existing local branch with the lane's name is NOT the claim — leave it,
    // and print no checkout recipe that would land on the wrong tip
    note(`a local branch ${ref} already existed here — left untouched: local ${ref} vs origin/${ref} (the lane at origin) must be reconciled by hand before working`)
  } else {
    branched = G('branch', ref, sha) !== null
    if (branched) {
      // upstream resolves through the FETCH REFSPEC, not the tracking ref — a
      // single-branch clone refuses ("not a branch") until the lane is opted into
      // the refspec (what `git remote set-branches --add` does); detected by the
      // refusal itself, never by parsing refspecs
      if (G('branch', `--set-upstream-to=origin/${ref}`, ref) === null) {
        G('config', '--add', 'remote.origin.fetch', `+refs/heads/${ref}:refs/remotes/origin/${ref}`)
        G('branch', `--set-upstream-to=origin/${ref}`, ref)
      }
      checkout = G('checkout', ref) !== null
    }
  }
  return { branched, checkout }
}

function runClaim(argv) {
  if (argv[0] === '--help' || argv[0] === '-h') { console.log(`baseline lane claim — claim a work lane: atomic branch creation at origin\n  ${LANE_USAGE}\n  exit: 0 claimed (or already this agent's) · 2 usage/refusal/environment · 3 claimed by another agent`); return 0 }
  const opt = makeOpt(argv)
  const usage = msg => { console.error(`baseline lane claim: ${msg}\n  ${LANE_USAGE}`); return 2 }
  for (const f of VALUE_FLAGS) if (opt(f, null) === true) return usage(`${f} needs a value`)
  const JSON_OUT = !!opt('--json', false)
  const notes = []
  const note = s => { notes.push(s); if (!JSON_OUT) console.log(`  · ${s}`) }

  // the issue number is the one positional (accepts '#22' and '22')
  const skipValue = new Set(VALUE_FLAGS)
  let issueArg = null
  for (let i = 0; i < argv.length; i++) {
    if (skipValue.has(argv[i])) { i++; continue }
    if (argv[i].startsWith('-')) continue
    issueArg = argv[i]; break
  }
  if (!issueArg) return usage('which issue? — pass the issue number (the lane anchors to it)')
  const issue = String(issueArg).replace(/^#/, '')
  if (!/^[1-9][0-9]*$/.test(issue)) return usage(`'${issueArg}' is not an issue number`)

  const REPO = path.resolve(String(opt('--repo', process.cwd())))
  const repo = liteRepo(REPO) // claim reads the descriptor and talks to origin — no tree walk
  const G = (...a) => run('git', ['-C', REPO, ...a])

  const gates = descriptorGates(repo, usage, 'claim')
  if (typeof gates === 'number') return gates
  const { d, ns } = gates
  const ref = ns.replace('*', issue)
  if (run('git', ['check-ref-format', `refs/heads/${ref}`]) === null) return usage(`'${ref}' is not a valid branch name (from lanes.namespace '${ns}')`)
  const agent = resolveAgent(opt('--agent', null), REPO)

  // ---- origin is the rendezvous (ADR-0009 Rule 5) — no origin, no claim ----
  if (G('remote', 'get-url', 'origin') === null) return usage('no origin remote — the lane rendezvous is ref creation at origin; add one (git remote add origin ...)')

  // ---- issue verification: the posture decides whether the forge is even asked ----
  const workflow = d.data.workflow
  const pf = workflow === 'multi-lane-local' ? null : probeForge(repo)
  const forge = makeForge(repo, { available: !!pf?.available, nwo: pf?.repo || null, posture: workflow })
  if (!forge.available) {
    note(forge.source === 'posture' ? forge.reason : `issue #${issue} unverified (${pf?.reason || forge.reason}) — proceeding; the push decides`)
  } else {
    const it = forge.issue(issue)
    const state = it ? String(it.state || '').toLowerCase() : null
    if (state === 'open') note(`issue #${issue} open${it.title ? `: "${it.title}"` : ''}`)
    else if (state) return usage(`issue #${issue} is ${state}${it.title ? ` ("${it.title}")` : ''} — claiming it is divergence at birth (DIV-01). Reopen it first (gh issue reopen ${issue}) or claim an open issue.`)
    else note(`issue #${issue} unverified (forge returned no state) — proceeding; the push decides`)
  }

  // ---- ONE preflight round trip answers three questions: origin reachable? what is
  // origin's HEAD (the default-branch fallback)? does the lane ref exist already? ----
  const pre = run('git', ['-C', REPO, 'ls-remote', '--symref', 'origin', 'HEAD', `refs/heads/${ref}`], { timeout: 30000 })
  if (pre === null) return usage('cannot reach origin (ls-remote failed) — nothing claimed')
  const preTip = pre.split('\n').find(l => l.endsWith(`\trefs/heads/${ref}`))?.split('\t')[0] || null
  let def = d.data.ground_truth_boundary?.default_branch
  if (!def) {
    def = pre.match(/^ref:\s+refs\/heads\/(\S+)\s+HEAD/m)?.[1] || null
    if (def) note(`default branch undeclared — origin HEAD says '${def}' (declare ground_truth_boundary.default_branch to pin it)`)
  }
  if (!def) return usage('no base to branch from — declare ground_truth_boundary.default_branch (origin HEAD did not resolve)')

  // ---- outcomes (closures over the resolved context; S4 — no parameter threading) ----
  const win = (sha, pushed) => {
    const { branched, checkout } = landLocal(G, ref, sha, note)
    if (JSON_OUT) { console.log(JSON.stringify({ claimed: true, ref, issue: +issue, agent, sha, base: def, pushed, checkout, notes }, null, 2)); return 0 }
    console.log(pushed
      ? `✓ claimed ${ref} (issue #${issue}) as ${agent} — ${sha.slice(0, 8)} pushed to origin`
      : `✓ lane ${ref} (issue #${issue}) already stands as this agent's claim (${agent}) — ${sha.slice(0, 8)} at origin`)
    if (branched && !checkout) console.log(`  branch created locally; switch when ready:  git checkout ${ref}`)
    console.log(`  next act: work the lane; record sessions as you go —  baseline log -m "..." --next "..."`)
    return 0
  }
  const lost = tip => {
    if (JSON_OUT) { console.log(JSON.stringify({ claimed: false, ref, issue: +issue, existing: tip, notes }, null, 2)); return 3 }
    console.log(`✗ lane ${ref} is already claimed at origin (tip ${String(tip).slice(0, 8)}) — you lost the race, cleanly: nothing was created here.`)
    console.log(`  next act:  baseline orient   (see live lanes + backlog, then claim a different issue)`)
    return 3
  }
  // an existing ref is a loss only if it is someone ELSE's: peek the tip's agent trailer
  // (a crashed claimer rerunning, or a fleet-mate sharing the agent identity, owns the lane)
  const settleExisting = tip => {
    let owner = null
    if (G('fetch', 'origin', `+refs/heads/${ref}:${PEEK_REF}`) !== null) {
      owner = (G('log', '-1', `--format=%(trailers:key=${TRAILER_AGENT},valueonly)`, PEEK_REF) || '').split('\n')[0].trim() || null
      G('update-ref', '-d', PEEK_REF)
    }
    if (owner && owner === agent) { note(`the existing claim carries this agent's own trailer — idempotent`); return win(tip, false) }
    return lost(tip)
  }
  if (preTip) return settleExisting(preTip)

  // ---- build the claim commit against origin's CURRENT tip, worktree untouched (DA-6) ----
  if (G('fetch', 'origin', `+refs/heads/${def}:${BASE_REF}`) === null) return usage(`cannot fetch origin ${def} — nothing claimed`)
  // ONE read for commit+tree: two reads of the ref would be a window (pid-unique names
  // already isolate rival processes; the single read removes the window entirely)
  const [base, tree] = (G('log', '-1', '--format=%H %T', BASE_REF) || '').split(' ')
  G('update-ref', '-d', BASE_REF) // best-effort tidy; a leftover is harmless (force-updated next claim)
  if (!base || !tree) return usage('claim base did not resolve after fetch — nothing claimed')
  const msg = `claim ${ref}: issue #${issue}\n\n${TRAILER_ISSUE}: #${issue}\n${TRAILER_AGENT}: ${agent}`
  const sha = G('commit-tree', tree, '-p', base, '-m', msg)
  if (!sha) return usage('commit-tree failed — is a git identity configured? (git config user.name / user.email)')

  // ---- THE claim: create the ref at origin; first push wins, atomically ----
  try {
    execFileSync('git', ['-C', REPO, 'push', 'origin', `${sha}:refs/heads/${ref}`], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'], timeout: 60000 })
  } catch (e) {
    // rejected, OR the transport died — ask origin what actually happened
    const now = run('git', ['-C', REPO, 'ls-remote', 'origin', `refs/heads/${ref}`], { timeout: 30000 })
    const tip = now ? now.split(/\s/)[0] : null
    if (tip === sha) { note('the push report was lost but origin holds this claim — won (transport hiccup after the ref landed)'); return win(sha, true) }
    if (tip) return settleExisting(tip)
    const why = String(e.stderr || e.message || '').split('\n').find(l => l.trim()) || 'push failed'
    return usage(`push failed (${why.trim()}) — nothing claimed`)
  }
  return win(sha, true)
}

function runReclaim(argv) {
  if (argv[0] === '--help' || argv[0] === '-h') { console.log(`baseline lane reclaim — take over a DERIVED-ABANDONED lane (dated takeover record; --jdg = the live-takeover escape hatch)\n  ${LANE_USAGE}\n  exit: 0 reclaimed (or the lane already stands under this agent's trailer) · 2 usage/refusal/environment · 3 lost race (the lane moved — it is active)`); return 0 }
  const opt = makeOpt(argv)
  const usage = msg => { console.error(`baseline lane reclaim: ${msg}\n  ${LANE_USAGE}`); return 2 }
  for (const f of VALUE_FLAGS) if (opt(f, null) === true) return usage(`${f} needs a value`)
  const JSON_OUT = !!opt('--json', false)
  const notes = []
  const note = s => { notes.push(s); if (!JSON_OUT) console.log(`  · ${s}`) }

  // the target is the one positional: an issue number ('7', '#7') or a full ref under the namespace
  const skipValue = new Set(VALUE_FLAGS)
  let target = null
  for (let i = 0; i < argv.length; i++) {
    if (skipValue.has(argv[i])) { i++; continue }
    if (argv[i].startsWith('-')) continue
    target = argv[i]; break
  }
  if (!target) return usage('which lane? — pass the issue number or the lane ref (see them: baseline orient)')

  const REPO = path.resolve(String(opt('--repo', process.cwd())))
  const repo = liteRepo(REPO)
  const G = (...a) => run('git', ['-C', REPO, ...a])

  const gates = descriptorGates(repo, usage, 'reclaim')
  if (typeof gates === 'number') return gates
  const { d, ns } = gates

  let issue, ref
  if (/^#?[1-9][0-9]*$/.test(target)) { issue = +String(target).replace(/^#/, ''); ref = ns.replace('*', String(issue)) }
  else {
    issue = issueOf(ns, target); ref = target
    if (issue == null) return usage(`'${target}' is neither an issue number nor an issue-anchored ref under lanes.namespace '${ns}' — reclaim stamps ${TRAILER_ISSUE} and refuses to invent one`)
  }
  if (run('git', ['check-ref-format', `refs/heads/${ref}`]) === null) return usage(`'${ref}' is not a valid branch name (from lanes.namespace '${ns}')`)
  const agent = resolveAgent(opt('--agent', null), REPO)
  const now = nowUTC()
  if (!now) return usage('BASELINE_LOG_NOW is not a parseable instant')
  const today = now.toISOString().slice(0, 10)

  if (G('remote', 'get-url', 'origin') === null) return usage('no origin remote — the lane rendezvous is ref creation at origin; add one (git remote add origin ...)')

  // ---- the posture decides whether the forge is consulted (one closure home, M5a) ----
  const workflow = d.data.workflow
  const pf = workflow === 'multi-lane-local' ? null : probeForge(repo)
  const forge = makeForge(repo, { available: !!pf?.available, nwo: pf?.repo || null, posture: workflow })
  if (!forge.available) note(forge.source === 'posture' ? forge.reason : `forge unreachable (${pf?.reason || forge.reason}) — leases derive from the git plane, low confidence`)

  // ---- fetch the lane into a private ref: the takeover base AND the owner/date source ----
  if (G('fetch', 'origin', `+refs/heads/${ref}:${RECLAIM_REF}`) === null) {
    // absent ref vs unreachable origin: ask once more, cheaply
    const probe = run('git', ['-C', REPO, 'ls-remote', 'origin', `refs/heads/${ref}`], { timeout: 30000 })
    if (probe === null) return usage('cannot reach origin (ls-remote failed) — nothing reclaimed')
    if (!probe.trim()) return usage(`no claim exists at origin for ${ref} — nothing to reclaim (claim it instead: baseline lane claim ${issue})`)
    return usage(`cannot fetch origin ${ref} — nothing reclaimed`)
  }
  // ONE read for tip commit + tree — the pair the takeover is built from must be one
  // consistent observation, never two reads with a window between them
  const [tip, tree] = (G('log', '-1', '--format=%H %T', RECLAIM_REF) || '').split(' ')
  if (!tip || !tree) return usage('reclaim base did not resolve after fetch — nothing reclaimed')
  const from = laneOwner(REPO, RECLAIM_REF, issue)

  // ---- ONE derivation (the same gathering orient renders) decides reclaimability ----
  const ttl = d.data.lanes?.lease_ttl ?? DEFAULT_LEASE_TTL
  const ttlMs = parseTtlMs(ttl) ?? parseTtlMs(DEFAULT_LEASE_TTL)
  const gathered = gatherLaneFacts(repo, forge, ns, { defaultBranch: d.data.ground_truth_boundary?.default_branch ?? null })
  let laneFact = gathered.lanes.find(l => l.ref === ref) || null
  if (!laneFact || laneFact.tip !== tip) {
    // the forge's refs page may lag, truncate, or (under replay) fossilize — a state
    // derived from a DIFFERENT commit than the takeover's parent would let a stale
    // answer steal a live lane, so on any tip mismatch the freshness is rebuilt from
    // the fetched git objects. The forge's PR-activity signal is kept: it can only
    // err toward LIVE, the safe direction.
    const prUpdatedAt = laneFact?.prUpdatedAt ?? null
    note(laneFact
      ? `the ${gathered.source === 'forge' ? "forge's" : 'gathered'} lane answer names a different tip than the fetch (${String(laneFact.tip).slice(0, 8)} vs ${tip.slice(0, 8)}) — freshness rebuilt from fetched git objects`
      : `lane absent from ${gathered.source === 'forge' ? "the forge's lane listing" : gathered.source === 'git' ? "origin's ref listing" : 'every lane listing'} — freshness read from fetched git objects (low confidence)`)
    // the rebuilt fact keeps the COMPLETED exemption honest: recompute merged for
    // THIS tip, or a reclaim on stale forge data would un-complete finished work
    const db = d.data.ground_truth_boundary?.default_branch ?? null
    const mergedBase = db ? (['origin/' + db, db].find(r => G('rev-parse', '--verify', '-q', r + '^{commit}') !== null) || null) : null
    laneFact = { ref, tip, committedDate: G('log', '-1', '--format=%cI', RECLAIM_REF) || null, prUpdatedAt, pr: laneFact?.pr ?? null, agent: from, agentSource: from ? 'history-trailer' : null, source: 'git', merged: !!(mergedBase && G('merge-base', '--is-ancestor', tip, mergedBase) !== null) }
  }
  const view = deriveLanes({ lanes: [laneFact], ttlMs, now: now.toISOString(), namespace: ns })[0]
  const idle = view.age_ms == null ? 'age unresolvable' : `${Math.floor(view.age_ms / 3600000) < 48 ? Math.floor(view.age_ms / 3600000) + 'h' : Math.floor(view.age_ms / 86400000) + 'd'} idle`

  const jdgId = opt('--jdg', null)
  let jdgUsed = null

  const lost = movedTip => {
    if (JSON_OUT) { console.log(JSON.stringify({ reclaimed: false, ref, issue, agent, from, existing: movedTip, state: view.state, notes }, null, 2)); return 3 }
    console.log(`✗ reclaim lost: ${ref} moved at origin while reclaiming (tip ${String(movedTip).slice(0, 8)}) — the lane is active; re-derive before trying again:  baseline orient`)
    return 3
  }
  // landSha is what origin actually holds — our pushed takeover, or a rival takeover
  // under this agent's own identity (adopted, never our unpushed sha)
  const win = (landSha, pushed) => {
    const { branched, checkout } = landLocal(G, ref, landSha, note)
    // the dated takeover record, machine-written through the ONE record writer (scrub
    // gate included) — spawned so its output (and --json envelope) stays its own.
    // Written AFTER the landing attempt so a successful checkout puts it on the lane.
    let record = null
    const BASELINE = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'baseline.mjs')
    const logMsg = `Reclaimed ${ref} (issue #${issue}) from ${from ?? 'an unknown agent (no trailer found)'}: derived ${view.state ?? 'UNDERIVED'}, ${idle} of ttl ${ttl}${jdgUsed ? `, live takeover under ${jdgUsed.id}` : ''}. Takeover commit ${landSha.slice(0, 8)} (observed tip ${tip.slice(0, 8)} at derivation).`
    const rl = spawnSync(process.execPath, [BASELINE, 'log', '--json', '--repo', REPO, '--lane', ref, '--agent', agent, '-m', logMsg, '--next', `resume issue #${issue}: read this lane's prior session records, then continue the work`], { encoding: 'utf8' })
    let logEnv = null
    try { logEnv = JSON.parse(rl.stdout || '{}'); record = logEnv.written ?? null } catch { record = null }
    if (!record) {
      // a scrub block is NON-LOSSY (M4's pinned UX): relay the draft, the finding ids,
      // and the exact rerun — never the envelope's opening brace as a "reason"
      if (logEnv?.blocked?.length) {
        note(`takeover record scrub-BLOCKED (${logEnv.blocked.map(b => b.name).join(', ')}) — draft kept: ${logEnv.draft ?? '(no draft reported)'}`)
        note(`real secret? rotate it, edit the draft, rerun:  baseline log --from ${logEnv.draft}`)
        note(`false positive? rerun with the dated judgment:  baseline log --from ${logEnv.draft}${logEnv.blocked.map(b => ` --allow ${b.id}`).join('')} --allow-reason "why this is not a secret" (ensure .baseline/cache/ is gitignored BEFORE committing)`)
      } else {
        const why = (rl.stderr || '').split('\n').find(l => l.trim())?.trim() || 'log failed'
        note(`takeover record NOT written (${why}) — write it by hand: baseline log -m "takeover of ${ref}" --lane ${ref}`)
      }
    }
    for (const w of logEnv?.warned ?? []) note(`record heuristic finding (written anyway): ${w.name} (${w.masked ?? ''}) — silence: --allow ${w.id} --allow-reason "..."`)
    // best-effort issue comment — posture/reachability-gated, and honestly labeled when skipped
    let comment = 'skipped'
    if (forge.source === 'posture') comment = `skipped: ${forge.reason}`
    else if (forge.source === 'replay') comment = 'skipped: forge replay (no writes)'
    else if (!forge.available) comment = 'skipped: forge unreachable'
    else comment = gh(['issue', 'comment', String(issue), '--body', `\`baseline lane reclaim\`: ${agent} took over \`${ref}\` (was ${from ?? 'unowned'}; derived ${view.state ?? 'UNDERIVED'}, ${idle} of ttl ${ttl}${jdgUsed ? `; live takeover under ${jdgUsed.id}` : ''}).`], { cwd: REPO }) !== null ? 'posted' : 'failed (best-effort — post by hand: gh issue comment)'
    if (comment !== 'posted') note(`issue comment ${comment}`)
    if (JSON_OUT) { console.log(JSON.stringify({ reclaimed: true, ref, issue, agent, from, sha: landSha, state: view.state, pushed, branched, checkout, record, comment, notes }, null, 2)); return 0 }
    console.log(`✓ reclaimed ${ref} (issue #${issue}) as ${agent} — takeover ${landSha.slice(0, 8)} ${pushed ? 'pushed to origin' : 'already at origin'} (was ${from ?? 'unowned'}, derived ${view.state ?? 'UNDERIVED'} · ${idle} of ttl ${ttl})`)
    if (record) console.log(`  record: ${record}`)
    if (branched && !checkout) console.log(`  branch created locally but NOT checked out; switch when ready:  git checkout ${ref}`)
    console.log(`  next act: read the lane's prior session records, then work it${checkout ? '' : ` ON THE LANE (a log written elsewhere lands on the wrong branch)`} —  baseline log -m "..." --next "..."`)
    return 0
  }

  // ---- the gate: derived ABANDONED, or an unexpired deviation JDG naming this lane ----
  // A lane already standing under this agent's own trailer is an idempotent completion,
  // not a takeover to justify: a reclaimer that pushed and crashed before the record must
  // not be told to mint a deviation judgment against its own lane (claim's rerun rule).
  if (view.state !== 'ABANDONED' && from && from === agent) {
    note(`the lane already stands under this agent's trailer — completing the takeover (idempotent, nothing pushed)`)
    return win(tip, false)
  }
  if (view.state !== 'ABANDONED') {
    if (typeof jdgId !== 'string') {
      if (view.state === 'COMPLETED') return usage(`${ref} derives COMPLETED — its tip is already merged into the default branch; there is nothing to reclaim. Prune it (git push origin --delete ${ref}) and claim fresh work.`)
      return usage(`${ref} derives ${view.state ?? 'UNDERIVED'} (${idle} of ttl ${ttl}) — reclaim requires a derived ABANDONED. A live takeover needs a deviation judgment naming the lane:\n    baseline jdg new --kind deviation --subject "${ref}" --reason "..." --review-by YYYY-MM-DD\n    baseline lane reclaim ${issue} --jdg JDG-NNNN`)
    }
    const { records } = loadJudgments(REPO)
    const j = records.find(r => r.id === jdgId)
    if (!j) return usage(`--jdg ${jdgId} does not resolve to a valid judgment in records/judgments/`)
    if (j.kind !== 'deviation') return usage(`--jdg ${jdgId} is a ${j.kind} — the live-takeover escape hatch honors only kind: deviation`)
    if (j.review_by < today) return usage(`--jdg ${jdgId} lapsed (review_by ${j.review_by}) — an expired judgment authorizes nothing; re-judge it first`)
    if (!new RegExp(`(^|[^\\w/])${escRe(ref)}([^\\w/]|$)`).test(String(j.subject))) return usage(`--jdg ${jdgId} names '${j.subject}', not this lane (${ref}) — the judgment must name the lane it takes over`)
    jdgUsed = j
    note(`live takeover honored by ${j.id} (deviation by ${j.by}, review by ${j.review_by}) — lane derives ${view.state ?? 'UNDERIVED'}`)
  } else if (from && from === agent) {
    note(`renewing this agent's own abandoned lane (the takeover commit refreshes the lease)`)
  }

  // ---- the takeover: a child of the observed tip, SAME tree (read in the one shot
  // above), new trailer. Pushed under an exact-value CAS (--force-with-lease=ref:tip):
  // a plain push would silently RECREATE a lane deleted mid-flight (a merged PR's
  // auto-delete targets exactly the stale lanes reclaim targets) and fast-forward over
  // a force-rewound one — the lease pins origin to the very tip the state was derived
  // from, so ANY move mid-flight rejects and the re-ask names the truth ----
  G('update-ref', '-d', RECLAIM_REF) // best-effort tidy; a leftover is harmless (pid-unique + force-updated next reclaim)
  const msg = `reclaim ${ref}: issue #${issue} takeover\n\n${TRAILER_ISSUE}: #${issue}\n${TRAILER_AGENT}: ${agent}`
  const sha = G('commit-tree', tree, '-p', tip, '-m', msg)
  if (!sha) return usage('commit-tree failed — is a git identity configured? (git config user.name / user.email)')

  try {
    execFileSync('git', ['-C', REPO, 'push', `--force-with-lease=refs/heads/${ref}:${tip}`, 'origin', `${sha}:refs/heads/${ref}`], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'], timeout: 60000 })
  } catch (e) {
    // rejected (the lane moved — someone pushed work or a rival takeover; or it vanished)
    // OR the transport died — ask origin what actually happened, exactly like claim
    const nowLs = run('git', ['-C', REPO, 'ls-remote', 'origin', `refs/heads/${ref}`], { timeout: 30000 })
    if (nowLs === null) return usage(`push did not report success AND origin is unreachable for the re-ask — the takeover state is UNKNOWN (it may have landed); re-run when origin returns: a rerun settles idempotently`)
    const seen = nowLs.split(/\s+/)[0] || null
    if (seen === sha) { note('the push report was lost but origin holds this takeover — won (transport hiccup after the ref landed)'); return win(sha, true) }
    if (!seen) return usage(`${ref} vanished at origin while reclaiming (deleted mid-flight — a merged PR's auto-delete?) — nothing reclaimed, nothing recreated; re-orient before retrying`)
    if (seen && seen !== tip) {
      // a rival takeover under this agent's OWN identity is a win we didn't push —
      // adopt origin's tip (never land our unpushed sha, which origin never saw)
      if (G('fetch', 'origin', `+refs/heads/${ref}:${PEEK_REF}`) !== null) {
        const owner = (G('log', '-1', `--format=%(trailers:key=${TRAILER_AGENT},valueonly)`, PEEK_REF) || '').split('\n')[0].trim() || null
        G('update-ref', '-d', PEEK_REF)
        if (owner && owner === agent) { note(`the moved tip carries this agent's own trailer — a rival reclaim under this identity won; adopting origin's tip`); return win(seen, false) }
      }
      return lost(seen)
    }
    const why = String(e.stderr || e.message || '').split('\n').find(l => l.trim()) || 'push failed'
    return usage(`push failed (${why.trim()}) — nothing reclaimed`)
  }
  return win(sha, true)
}
