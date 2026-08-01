// baseline admit — merge-point revalidation (M6a; C30/C35, FS1, FS5, C33 as amended
// by the M6 ruling, PLAN §8). "A verdict is valid only for the state it evaluated."
//
// Refusal is THIS COMMAND's contract, joined since M7a by the promoted blockers.
// Admit exits nonzero on exactly:
//   (a) C35 staleness — the target tip is not an ancestor of the admitted HEAD
//       (deterministic git ancestry, evaluated before any rule);
//   (b) any admit-context blocker-severity FAIL or DIVERGED (isBlocking — DESC-03
//       plus the M7a-promoted FLOW/DIV/MERGE set; EXCLUDED under the JDG-only
//       admission path, whose ruled shape precludes lane records);
//   (c) required-source loss on admit's GATING facts (target resolution → exit 2,
//       nothing evaluated; ancestry provability and DESC-03's range diff → refusal) —
//       a warn rule's unreachable source SKIPs labeled, exactly as in check:
//       advisory findings never acquire blocker-grade denial power via
//       unavailability. Relief for (c) alone: an unexpired break-glass JDG with
//       gate:admit read FROM THE TARGET REF (FS5 — never from the incoming branch).
//       Staleness is data-plane truth and DESC-03's relief is its own same-PR JDG;
//       neither is break-glass-relievable.
//
// The JDG-only admission path (the ruling's reachable relief valve): a range that is
// NOTHING BUT schema-valid additions under records/judgments/, carrying at least one
// unexpired break-glass gate:admit, admits from tree+history facts alone — the forge
// is closed for the run (one-home closure in makeForge, replay included), so the
// relief PR never depends on the plane whose loss it relieves.
//
// FS1: the descriptor that governs the run is read from the TARGET ref — a PR cannot
// weaken the posture that judges it; the branch-local descriptor is advisory-only.
//
// Exit: 0 admitted (warn/diverged findings ride the output) · 1 refused (stale /
// blocker FAIL / gating-source loss) · 2 usage or environment (nothing evaluated).
import path from 'node:path'
import { makeOpt, makeOptAll, nowUTC, sanitizeTTY, globToRe, issueOf } from './util.mjs'
import { loadRules } from './rules.mjs'
import { indexRepo } from './repo.mjs'
import { laneOrNull, run } from './probe.mjs'
import { resolveConfig } from './config.mjs'
import { makeEvalCheck } from './evaluators.mjs'
import { makeLaneWorld } from './facts/index.mjs'
import { runRules } from './engine.mjs'
import { CATS, makeColor, isBlocking } from './report.mjs'
import { DESCRIPTOR_FILE, DESCRIPTOR_SCHEMA } from './descriptor.mjs'
import { validateAgainst } from './validate.mjs'
import { loadJudgmentsAt, selectBreakGlass, JUDGMENTS_DIR, JDG_PARSE_CAP } from './jdg.mjs'
import { inputsDigest, provenanceLine, provenanceJson } from './digest.mjs'
import { validateRecord } from './records.mjs'

const USAGE = `usage: baseline admit [--repo DIR] [--target REF] [--json] [--profile P] [--config FILE]`

export function runAdmit(argv) {
  if (argv[0] === '--help' || argv[0] === '-h') {
    console.log(`baseline admit — merge-point revalidation: a verdict is valid only for the state it evaluated\n  ${USAGE}\n  exit: 0 admitted · 1 refused (stale / blocker / gating-source loss) · 2 usage/environment`)
    return 0
  }
  const opt = makeOpt(argv), optAll = makeOptAll(argv)
  const usage = msg => { console.error(`baseline admit: ${msg}\n  ${USAGE}`); return 2 }
  for (const f of ['--repo', '--target', '--config']) if (opt(f, null) === true) return usage(`${f} needs a value`)
  const REPO = path.resolve(String(opt('--repo', process.cwd())))
  const JSON_OUT = !!opt('--json', false)
  const color = makeColor(JSON_OUT)
  const now = nowUTC()
  if (!now) return usage('BASELINE_LOG_NOW is not a parseable instant')
  const today = now.toISOString().slice(0, 10)

  const repo = indexRepo(REPO)
  if (!repo.HEAD) return usage('not a git repository (no HEAD) — admit judges a commit against a target ref')
  const g = (...a) => run('git', ['-C', REPO, ...a])

  // ---- target resolution (gating fact; unresolvable = exit 2, nothing evaluated) ----
  const explicit = opt('--target', null)
  let targetRef = typeof explicit === 'string' ? explicit : null
  let fetchNote = null
  if (!targetRef) {
    if (g('remote', 'get-url', 'origin') === null) return usage('no origin remote and no --target — admit needs a target to re-derive against')
    // fresh target is the point — bounded best-effort fetch; failure degrades to the
    // local remote-tracking ref, LABELED (the verdict binds to the SHA it names; the
    // forge-side up-to-date binding is what guards a moved target, not this fetch)
    if (run('git', ['-C', REPO, 'fetch', '--quiet', 'origin'], { timeout: 60000 }) === null) fetchNote = 'fetch failed — target read from the last-fetched local ref'
    const sym = g('symbolic-ref', '--quiet', 'refs/remotes/origin/HEAD')
    let branch = sym ? sym.replace(/^refs\/remotes\/origin\//, '') : null
    if (!branch) {
      // origin/HEAD unset locally (common) — ask origin itself, never guess (M5a idiom)
      const ls = run('git', ['-C', REPO, 'ls-remote', '--symref', 'origin', 'HEAD'], { timeout: 30000 })
      branch = ls?.match(/^ref: refs\/heads\/(\S+)\tHEAD/m)?.[1] || null
    }
    if (branch) targetRef = `origin/${branch}`
  }
  const resolveTip = ref => ref && repo.gitObjExists(`${ref}^{commit}`) ? g('rev-parse', `${ref}^{commit}`) : null
  let targetTip = resolveTip(targetRef)
  if (!targetTip && !explicit) return usage(`no target resolves (origin/HEAD unknown and nothing fetched) — pass --target <ref>, or fetch the default branch first`)
  if (!targetTip) return usage(`--target '${targetRef}' does not resolve to a commit here — fetch it first`)

  // ---- the governing descriptor: read from the TARGET ref (FS1) ----
  // Read AT THE RESOLVED TIP, not the mutable ref name: a concurrent fetch (editor
  // autofetch, a parallel admit) moving origin/<db> between rev-parse and `git show`
  // would split the verdict across two commits — it binds to the SHA it names.
  let cfgRes = resolveConfig(repo, { cliConfigPath: opt('--config', null), profileArgs: optAll('--profile'), descriptorRef: targetTip })
  let DESCRIPTOR = cfgRes.DESCRIPTOR
  // when the target was DERIVED, the descriptor's own declared default_branch wins over
  // the origin/HEAD mirror config (stored intent > forge mirror) — switch and re-read
  const declared = DESCRIPTOR.valid ? DESCRIPTOR.data.ground_truth_boundary?.default_branch : null
  if (!explicit && declared && targetRef !== `origin/${declared}`) {
    const t = resolveTip(`origin/${declared}`)
    if (t) {
      targetRef = `origin/${declared}`; targetTip = t
      cfgRes = resolveConfig(repo, { cliConfigPath: opt('--config', null), profileArgs: optAll('--profile'), descriptorRef: targetTip })
      DESCRIPTOR = cfgRes.DESCRIPTOR
    } else {
      return usage(`the target descriptor declares default_branch '${sanitizeTTY(declared)}' but origin/${sanitizeTTY(declared)} does not resolve here — fetch it, or pass --target`)
    }
  }
  if (!DESCRIPTOR.present) return usage(`no ${DESCRIPTOR_FILE} at ${targetRef} — admit judges by the target's declared posture (FS1); adopt a descriptor on the target branch first`)
  if (!DESCRIPTOR.valid) return usage(`${DESCRIPTOR_FILE} at ${targetRef} is invalid (${DESCRIPTOR.errors.slice(0, 2).join('; ')}) — fix it on the target branch; a broken target posture cannot judge anything`)
  const { cfg, ACTIVE, CLAIMS_ACTIVE, CLAIMS_REASON, JDGS } = cfgRes

  // ---- C35 staleness: command-level, before any rule ----
  const HEADSHA = g('rev-parse', 'HEAD')
  const anc = repo.gitIsAncestor(targetTip, 'HEAD') // 0 ancestor · 1 not · other/err indeterminate
  const shallow = repo.gitIsShallow()
  const stale = anc === 1 && !shallow
  const indeterminate = anc !== 0 && !stale

  // ---- break-glass relief, read FROM THE TARGET (FS5) — covers (c) only ----
  const targetLedger = loadJudgmentsAt(REPO, targetTip)
  const relief = selectBreakGlass(targetLedger.records, 'admit', today)

  // ---- the admitted range + the JDG-only admission path ----
  // no-renames: rename detection would collapse `git mv baseline.repo.json away` into
  // one post-image name and DESC-03 would read the descriptor as untouched (the review
  // panel's rename-bypass). Admit's range is judged as honest deletes + adds.
  const changed = repo.gitDiffNames(`${targetTip}...HEAD`, null, { noRenames: true })
  const added = repo.gitDiffNames(`${targetTip}...HEAD`, null, { addedOnly: true, noRenames: true })
  // parse cap (one-homed in jdg.mjs at M7c): every other fan-out here is bounded
  // (sisters 100, DIV refs 20) — a PR adding thousands of judgment files must not
  // buy thousands of git spawns. Beyond the cap: DESC-03 stays fail-closed (an
  // out-of-cap judgment doesn't satisfy it) and the JDG-only path is off
  // (unvalidated riders never take the privileged path).
  const addedJdgPaths = (added || []).filter(p => p.startsWith(JUDGMENTS_DIR + '/'))
  const jdgCapped = addedJdgPaths.length > JDG_PARSE_CAP
  const addedJudgments = addedJdgPaths.slice(0, JDG_PARSE_CAP).map(rel => {
    let record = null, errors = []
    const raw = repo.gitCatFile('HEAD', rel)
    if (raw === null) errors = ['blob unreadable at HEAD']
    else {
      try { record = JSON.parse(raw) } catch { errors = ['not valid JSON'] }
      if (record) {
        errors = validateRecord('judgment', record)
        // same discipline as the ledger loaders: the id IS the filename
        if (!errors.length && record.id !== rel.split('/').pop().replace(/\.json$/, '')) errors = [`id '${record.id}' does not match filename`]
        if (errors.length) record = null
      }
    }
    return { rel, record, errors }
  })
  // the ruling's shape is strict: NOTHING BUT additions under records/judgments/ that
  // ALL schema-validate — one invalid rider and the range falls to the normal contract
  // (a privileged path must never carry unvalidated content onto main's ledger)
  const jdgOnlyShape = changed !== null && changed.length > 0 && added !== null && added.length === changed.length && changed.every(p => p.startsWith(JUDGMENTS_DIR + '/'))
  const jdgReliefs = (jdgOnlyShape && !jdgCapped && addedJudgments.every(j => j.record)) ? addedJudgments.filter(j => j.record.kind === 'break-glass' && j.record.gate === 'admit' && j.record.review_by >= today) : []
  const jdgOnly = jdgReliefs.length > 0

  // ---- the admit world the rules evaluate through ----
  const BRANCH = laneOrNull(repo) || process.env.GITHUB_HEAD_REF || null
  const DEFAULT_BRANCH = declared || targetRef.replace(/^origin\//, '')
  const ns = DESCRIPTOR.data.lanes?.namespace || null
  let sisters = [], sistersCapped = false
  if (ns && BRANCH) {
    const dir = String(ns).slice(0, String(ns).lastIndexOf('/', String(ns).indexOf('*')) + 1)
    const re = globToRe(ns)
    const out = g('for-each-ref', '--format=%(refname:short) %(objectname)', `refs/remotes/origin/${dir}`) || ''
    for (const line of out.split('\n').filter(Boolean)) {
      const [short, tip] = line.split(' ')
      const ref = short.replace(/^origin\//, '')
      if (ref === BRANCH || !re.test(ref)) continue
      if (sisters.length >= 100) { sistersCapped = true; break }
      sisters.push({ ref, tip })
    }
  }
  // 64MB buffer: a big range's commit bodies overflowing run()'s 1MB default would
  // silently drop every Baseline-Stacked-On declaration → false MERGE-02 warns
  const trailerRaw = run('git', ['-C', REPO, 'log', '--format=%B', `${targetTip}..HEAD`], { maxBuffer: 64 * 1024 * 1024 }) || ''
  const stackedOn = [...trailerRaw.matchAll(/^Baseline-Stacked-On:[ \t]*(\S+)[ \t]*$/gm)].map(m => m[1])
  let headDescriptor = { present: false, valid: false, data: null, errors: [] }
  const headDescRaw = repo.gitCatFile('HEAD', DESCRIPTOR_FILE)
  if (headDescRaw !== null) {
    headDescriptor.present = true
    try {
      const data = JSON.parse(headDescRaw); const errors = []
      validateAgainst(data, DESCRIPTOR_SCHEMA, '', errors)
      headDescriptor = { present: true, valid: errors.length === 0, data, errors }
    } catch { headDescriptor.errors = ['not valid JSON'] }
  }
  const ADMITWORLD = {
    targetRef, targetTip, headSha: HEADSHA, changed, added, addedJudgments, jdgCapped, jdgOnly, sisters, sistersCapped, stackedOn, headDescriptor,
    mergeBase: (a, b) => g('merge-base', a, b),
  }
  const LANEWORLD = makeLaneWorld(repo, DESCRIPTOR, { forgeClosed: jdgOnly ? 'forge not consulted (JDG-only admission path)' : null })
  // NO_EXEC: no exec-kind rule declares admit context (BUILD-05 is check's crown); the
  // fallback binding re-runs the check required check at the merge-relevant SHA instead
  // (F8 as ruled — the crown never runs twice per SHA because it never runs here at all)
  const evalCheck = makeEvalCheck({ repo, cfg, NO_EXEC: true, JDGS, DESCRIPTOR, BRANCH, DEFAULT_BRANCH, LANEWORLD, ADMITWORLD })
  const RULES = loadRules()
  const results = runRules({ rules: RULES.rules, cfg, ACTIVE, CLAIMS_ACTIVE, CLAIMS_REASON, evalCheck, DESCRIPTOR, BRANCH, DEFAULT_BRANCH, context: 'admit' })

  // ---- provenance (M6c): the inputs_digest receipt — REFUSAL-INERT by contract.
  // Assembly never touches refusals/results/summary; every lost source digests as
  // a labeled VALUE ('not consulted' / 'none'), never a refusal and never a hole.
  // checkRuns(HEAD) is admit's one marginal forge read (F8's fold) — the same
  // one-home closure that gates the lane world degrades it under posture/JDG-only.
  const provWorld = LANEWORLD()
  const provRunsRaw = provWorld.forge.checkRuns(HEADSHA)
  const provTuples = Array.isArray(provRunsRaw?.check_runs) ? provRunsRaw.check_runs.map(r => ({ name: r.name, conclusion: r.conclusion, head_sha: r.head_sha })) : null
  // no anchor is 'none', never issueState(null) — the world has no no-anchor value
  const provAnchorNum = (ns && BRANCH) ? issueOf(ns, BRANCH) : null
  const provAnchor = provAnchorNum == null ? null : { issue: provAnchorNum, state: provWorld.issueState(provAnchorNum) }
  const provInputs = { head: HEADSHA, target: targetTip, descriptorOid: repo.gitBlobAt(targetTip, DESCRIPTOR_FILE), rulesVersion: RULES.version, checkRuns: provTuples, anchor: provAnchor }
  const provenance = provenanceJson({ digest: inputsDigest(provInputs), ...provInputs })

  // ---- verdict assembly: (a) staleness · (b) blocker FAIL · (c) gating-source loss ----
  const refusals = []
  let breakGlass = null
  const ledgerNote = targetLedger.reachable ? '' : ` (the target ledger itself was unreadable at ${targetRef} — an existing break-glass could not be consulted)`
  if (stale) refusals.push(`stale: ${targetRef} @ ${targetTip.slice(0, 7)} is not an ancestor of HEAD — re-derive at an up-to-date SHA (merge/rebase the target, then rerun; the up-to-date branch-protection requirement is this refusal's forge-side twin)`)
  const sourceLoss = (why) => {
    if (relief) {
      if (breakGlass) breakGlass.covered += `; ${why}`
      else breakGlass = { id: relief.id, review_by: relief.review_by, covered: why }
    } else refusals.push(`${why}; relief: an unexpired break-glass JDG (gate: admit) on ${targetRef} — see CONTRACT.md${ledgerNote}`)
  }
  if (indeterminate) sourceLoss(shallow ? `history truncated (shallow clone) — ancestry not provable; fetch full history (actions/checkout: fetch-depth: 0)` : `ancestry check failed (git exit ${anc}) — target/HEAD relation unreadable`)
  // DESC-03's range diff is a gating fact (ruling leg c): a blocker that cannot see its
  // input must refuse, never silently SKIP into an admission (fail-open on the one
  // ruled-fail-closed rule). Same relief as the ancestry leg.
  if (!stale && !(indeterminate && !relief) && changed === null) sourceLoss(`the admitted range's diff (${targetRef}...HEAD) is unreadable — DESC-03's gating input is lost`)
  // M7a: leg (b) counts blocker-severity DIVERGED alongside FAIL — the verdict
  // class rides the refusal line (one predicate with the report exits: isBlocking).
  // EXCEPT under the JDG-only admission path: M6a's ruled promise is that a pure
  // judgment-additions range ADMITS from tree+history alone — its shape PRECLUDES
  // a session record, so a promoted lane-discipline blocker (FLOW-02 on the relief
  // branch) must never re-create the circularity the path exists to break. DESC-03
  // cannot fire there by construction (the descriptor is not in a jdg-only diff);
  // promoted findings still ride the output as rows, refusing nothing.
  const blockerFails = jdgOnly ? [] : results.filter(isBlocking)
  for (const x of blockerFails) refusals.push(`${x.r.id}${x.tag === 'DIVERGED' ? ' (DIVERGED)' : ''}: ${x.detail}`)
  const refused = refusals.length > 0
  const n = t => results.filter(x => x.tag === t).length
  const summary = { refusals: refusals.length, blockers: blockerFails.length, pass: n('PASS'), warn: n('WARN'), diverged: n('DIVERGED'), signoff: n('SIGN-OFF'), skip: n('SKIP'), total: results.length }

  if (JSON_OUT) {
    console.log(JSON.stringify({
      command: 'admit', repo: REPO, head: HEADSHA, branch: BRANCH,
      target: { ref: targetRef, sha: targetTip, source: explicit ? 'local-ref (explicit --target)' : fetchNote ? 'local-ref (fetch failed)' : 'fetched' },
      staleness: { ancestor: anc === 0, stale, indeterminate, shallow },
      jdgOnly, jdgRelief: jdgOnly ? jdgReliefs[0].record.id : null, breakGlass, verdict: refused ? 'REFUSED' : 'ADMITTED', refusals, provenance,
      results: results.map(x => ({ id: x.r.id, category: x.r.category, severity: x.r.severity, tag: x.tag, detail: x.detail })),
      summary, version: RULES.version, exit: refused ? 1 : 0,
    }, null, 2))
    return refused ? 1 : 0
  }

  const S = sanitizeTTY
  const TAG = { PASS: color(32, 'PASS'), FAIL: color(31, 'FAIL'), WARN: color(33, 'WARN'), DIVERGED: color(31, 'DIVERGED'), SKIP: color(90, 'SKIP'), 'SIGN-OFF': color(35, 'SIGN-OFF') }
  const TAGW = 8
  const tagCell = t => TAG[t] + ' '.repeat(Math.max(1, TAGW - t.length + 1))
  console.log(`\n  baseline admit v${RULES.version}  ·  ${path.basename(REPO)}  ·  HEAD ${HEADSHA.slice(0, 7)}${BRANCH ? ` (${S(BRANCH)})` : ''} → ${S(targetRef)} @ ${targetTip.slice(0, 7)}\n`)
  if (fetchNote) console.log(`  ⚠ ${fetchNote}\n`)
  if (jdgOnly) console.log(`  ◇ JDG-only admission path: the range is judgment records alone (${jdgReliefs[0].record.id}) — forge not consulted\n`)
  console.log(anc === 0 ? `  ✓ up to date: ${S(targetRef)} is an ancestor of HEAD` : breakGlass ? color(33, `  ⚠ admitted under break-glass ${breakGlass.id} from ${S(targetRef)} (review by ${breakGlass.review_by}) — ${S(breakGlass.covered)}`) : color(31, `  ✗ not admissible as-is (refusals below)`))
  console.log(color(90, `  ${provenanceLine({ digest: provenance.digest, ...provInputs })}`))
  console.log('')
  for (const cat of Object.keys(CATS)) {
    const rows = results.filter(x => x.r.category === cat); if (!rows.length) continue
    console.log('  ' + color(1, CATS[cat]))
    for (const x of rows) console.log(`    ${tagCell(x.tag)} ${x.r.id.padEnd(9)} ${S(x.r.title)}\n            ${color(90, '↳ ' + S(x.detail))}`)
    console.log('')
  }
  // one terse recap per refusal at the BOTTOM — where the eye lands — never a verbatim
  // duplicate of a FAIL row above (first clause, capped)
  for (const r of refusals) { const first = r.split(' — ')[0]; console.log(color(31, `  ✗ ${S(first.length > 140 ? first.slice(0, 137) + '…' : first)}`)) }
  console.log(refused
    ? color(31, `\n  ✗ REFUSED — ${refusals.length} refusal(s) · ${summary.warn} warn · ${summary.diverged} diverged (details above)\n`)
    : color(32, `\n  ✓ ADMITTED — HEAD ${HEADSHA.slice(0, 7)} vs ${S(targetRef)} @ ${targetTip.slice(0, 7)} · ${summary.pass} pass · ${summary.warn} warn · ${summary.diverged} diverged · ${summary.skip} n/a\n`))
  return refused ? 1 : 0
}
