// `baseline gen` — generators that write derivable/mechanical artifacts.
//
// M4c: `gen migrate-claims` — the C17 explosion of the V1 docs/CLAIMS.json
// monolith into per-claim records (idempotent by slug, O_EXCL, refusals loud).
//
// M6c: `gen index` + `gen --check` — C05 as amended (in-PR index views ONLY; the
// main-written snapshot ceremony and its hash/as_of headers are CUT):
//   - a generated view is a tracked markdown file whose FIRST line is the marker
//       <!-- baseline:generated <kind> — do not edit by hand; regenerate: baseline gen <kind> -->
//     Static text, byte-identical every run — no hash (regenerate-and-compare
//     needs none), no timestamp (determinism is ruled), no version (version-in-
//     marker would drift every view on every vendor bump; that case lives in the
//     REMEDY text instead).
//   - `gen index` derives docs/INDEX.md (or --out) from committed-shape content
//     ONLY — records ledgers + a docs map, everything sorted code-unit, dates
//     from filenames (the tool's one recency truth), links RELATIVE TO THE OUT
//     FILE's directory (CTX-05 resolves a doc's links against its own dir — a
//     root-relative link would break the consumer's md-links check).
//   - `gen --check` discovers marked views over the tracked pool (uncapped
//     reads — a size-capped read would silently green a big drifted view),
//     regenerates each in memory, byte-compares. Zero marked views → exit 0
//     (the ruled pre-adoption state). Drift → exit 1 with the remedy printed
//     VERBATIM-RUNNABLE (derived from this process's own argv — the consumer
//     invokes a vendored path, not a `baseline` binary). An unknown kind or an
//     unreadable discovered view → exit 1, named — never silently skipped.
//   - overwrite law: `gen index` writes over its own marker or into absence;
//     a file WITHOUT the marker is refused (move it aside or pass a different
//     --out — never paste the marker onto a hand-written file to authorize a
//     clobber). The refusal probe uses the same uncapped read.
import fs from 'node:fs'
import path from 'node:path'
import crypto from 'node:crypto'
import { makeOpt, sanitizeTTY } from './util.mjs'
import { indexRepo } from './repo.mjs'
import { resolveConfig } from './config.mjs'
import { validateRecord, recordSchema } from './records.mjs'
import { loadClaimRecords, loadLegacyClaims, CLAIM_RECORD_GLOB } from './claims.mjs'
import { loadJudgments } from './jdg.mjs'
import { SESSION_BASES } from './facts/git.mjs'

// ---- the generated-view contract (M6c) ----
export const MARKER_OF = (kind) => `<!-- baseline:generated ${kind} — do not edit by hand; regenerate: baseline gen ${kind} -->`
// Detection tolerates a BOM and CRLF on line 1 (they still byte-compare as drift
// — loud, correct); the marker's identity is the `baseline:generated <kind>` prefix.
export const MARKER_DETECT_RE = /^\uFEFF?<!--\s*baseline:generated\s+(\S+)[^>]*-->\r?$/
export const GEN_KINDS = new Set(['index'])

// The verbatim-runnable remedy: derived from THIS invocation's argv, repo-relative
// when the runner lives inside the target repo (the vendored-consumer reality —
// there is no `baseline` binary on any PATH).
export function remedyCommand(REPO, kind, outRel) {
  const self = path.resolve(process.argv[1] || 'baseline.mjs')
  const inRepo = self.startsWith(REPO + path.sep)
  // VERBATIM-runnable is the contract — a space-bearing path must survive the
  // reader's shell, so anything beyond the safe charset gets single-quoted
  const q = s => /^[A-Za-z0-9._/-]+$/.test(s) ? s : `'${String(s).replace(/'/g, `'\\''`)}'`
  return inRepo
    ? `node ${q(path.relative(REPO, self).split(path.sep).join('/'))} gen ${kind} --out ${q(outRel)} --repo .`
    : `node ${q(self)} gen ${kind} --out ${q(outRel)} --repo ${q(REPO)}`
}

// ---- the vendored-tree lock (M7c) ----
// C26's contraction endpoint: the consumption model STAYS vendored (the pointer
// flip is cut to V3 — the demo invokes tools/baseline/ at six sites incl. the
// required admit check; re-creating M6's relief circularity for no demonstrated
// demand is the classic contraction overreach). What ships is the pin: `gen lock`
// writes {version, tree_hash} and REC-06 (warn) compares — unpinned and skewed
// vendored trees stop being invisible. Paths are CANONICAL, not knobs: the tree
// at tools/baseline/, the lock BESIDE it (never inside — the lock must not hash
// itself). A tree vendored elsewhere is REC-06's documented SKIP, and S9's
// manual-copy paragraph (CONTRACT.md) names the canonical location.
export const VENDOR_TREE = 'tools/baseline'
export const VENDOR_LOCK = 'tools/baseline.lock.json'

// Deterministic tree hash: sha256 over `<relpath>\0<sha256(bytes)>\n` per file,
// paths sorted code-unit, bytes RAW (readText's 512KB/utf8 cap would corrupt a
// hash the way it silently greens a big view — same law, same exemption).
// The pool is a DEDICATED full walk of the tree, not the repo walker: the
// walker's SKIP_DIRS (node_modules, vendor, dist…) would be an undetectable
// rider channel inside the vendored copy — the pin must see EVERYTHING on disk
// (panel: lock-seam). Only `.git` is skipped, named and deliberate (a vendored-
// by-clone tree should shed it; its packfiles differ per clone and would make
// the pin machine-local). Worktree semantics: an untracked edit inside the
// vendored tree is a real skew — local stricter than CI, never the reverse.
// Symlinks and unreadable files are NOT hashed and NOT fatal here: they are
// collected so the writer can refuse (a tree that can't be fully read can't be
// pinned honestly) while the verifier degrades to a labeled WARN over the
// readable set — never a SKIP that would mask a concurrent real skew.
export function computeVendorLock(REPO, repo) {
  const files = [], unhashable = []
  const walkAll = (dir, rel) => {
    let ents; try { ents = fs.readdirSync(dir, { withFileTypes: true }) } catch { unhashable.push(`${rel}/ (unlistable)`); return }
    for (const e of ents) {
      if (e.name === '.git') continue
      const r = `${rel}/${e.name}`
      if (e.isSymbolicLink()) { unhashable.push(`${r} (symlink)`); continue }
      if (e.isDirectory()) walkAll(path.join(dir, e.name), r)
      else files.push(r)
    }
  }
  let rootIsDir = false
  try { rootIsDir = fs.lstatSync(path.join(REPO, VENDOR_TREE)).isDirectory() } catch {}
  if (rootIsDir) walkAll(path.join(REPO, VENDOR_TREE), VENDOR_TREE)
  if (!files.length && !unhashable.length) return { files: 0, unhashable }
  files.sort()
  const h = crypto.createHash('sha256')
  for (const f of files) {
    let buf
    try { buf = fs.readFileSync(path.join(REPO, f)) }
    catch { unhashable.push(`${f} (unreadable)`); continue }
    h.update(`${f}\0${crypto.createHash('sha256').update(buf).digest('hex')}\n`)
  }
  unhashable.sort()
  // version = the VENDORED tree's own declaration (its rules.json), never the
  // running engine's — the lock describes the tree it hashes
  let version = null
  try { version = JSON.parse(fs.readFileSync(path.join(REPO, VENDOR_TREE, 'rules.json'), 'utf8'))?.version ?? null } catch {}
  return { files: files.length, tree_hash: h.digest('hex'), version, unhashable }
}

const firstHeading = (md) => md.match(/^#\s+(.+?)\s*$/m)?.[1] ?? null
// Markdown-cell/link hygiene for repo-authored strings: a '|' or newline in a
// judgment subject must not split the table; '[' ']' in a title must not break
// the link (escaping ']' does NOT survive CTX-05's naive link regex — strip);
// a destination with spaces/parens rides in <...> (CommonMark; CTX-05 skips it).
const cell = s => String(s).replace(/\r?\n/g, ' ').replace(/\|/g, '∣')
const linkTitle = s => String(s).replace(/\r?\n/g, ' ').replace(/[[\]]/g, '')
const linkDest = s => /[\s()]/.test(s) ? `<${s}>` : s

// Deterministic index content over the repo's committed-shape surfaces. Pure of
// clock and machine: every list sorted code-unit, dates from filenames, titles
// from first headings (filename fallback — determinism has no hole).
export function generateIndex(repo, outRel) {
  const P = []
  P.push(MARKER_OF('index'))
  P.push('# Index')
  P.push('')
  P.push('_Generated view — edit the records, not this file. Regenerate: `baseline gen index`._')
  P.push('')
  // judgments ledger
  const { records: jdgs, findings: jdgBad } = loadJudgments(repo.REPO)
  P.push(`## Judgments (${jdgs.length}${jdgBad.length ? ` + ${jdgBad.length} invalid` : ''})`)
  P.push('')
  if (!jdgs.length) P.push('_none_')
  else {
    P.push('| id | kind | subject | review by |')
    P.push('|---|---|---|---|')
    for (const j of [...jdgs].sort((a, b) => a.id < b.id ? -1 : 1)) P.push(`| ${j.id} | ${j.kind} | ${cell(j.subject)} | ${j.review_by} |`)
  }
  P.push('')
  // claims ledger
  const claims = loadClaimRecords(repo)
  P.push(`## Claims (${claims.claims.length}${claims.errors.length ? ` + ${claims.errors.length} unreadable` : ''})`)
  P.push('')
  if (!claims.claims.length) P.push('_none_')
  else {
    P.push('| id | slug |')
    P.push('|---|---|')
    // _file tiebreak: claim ids are NOT filename-enforced (judgments are), so a
    // duplicate id must not leave row order to the fs walk — that would make the
    // committed view green on one machine and "drifted" on another
    for (const c of [...claims.claims].sort((a, b) => String(a.id) < String(b.id) ? -1 : String(a.id) > String(b.id) ? 1 : String(a._file) < String(b._file) ? -1 : 1)) P.push(`| ${cell(c.id)} | ${cell(c.slug ?? '')} |`)
  }
  P.push('')
  // session records by lane — count + newest DATE from the filename (the same
  // recency truth newestLocalLog and the forge listing already derive from).
  // Pool = tracked ∪ walked (M7c, ruled): `baseline log` never stages, so a
  // tracked-only pool makes log→regen→commit lag one session forever — the
  // committed view omits the record riding its own commit and CI's gen --check
  // reds it. The union sees the just-written record pre-add (parity with the
  // JSON ledgers, which already read the worktree) while the tracked side keeps
  // deleted-but-tracked records counted, exactly as before.
  const sessions = [...new Set([...repo.match(['records/sessions/**/*.md'], { tracked: true }), ...repo.match(['records/sessions/**/*.md'])])].sort()
  const byLane = new Map()
  for (const f of sessions) {
    const rest = f.slice('records/sessions/'.length)
    const cut = rest.lastIndexOf('/')
    // a record parked directly under records/sessions/ has no lane dir — it still
    // counts, honestly grouped, or the header total and the bullets would disagree
    const lane = cut < 1 ? '(unlaned)' : rest.slice(0, cut)
    const file = cut < 1 ? rest : rest.slice(cut + 1)
    const e = byLane.get(lane) || { n: 0, newest: '' }
    e.n++
    const d = file.match(/^(\d{4}-\d{2}-\d{2})/)?.[1] || ''
    if (d > e.newest) e.newest = d
    byLane.set(lane, e)
  }
  P.push(`## Session records (${sessions.length})`)
  P.push('')
  if (!byLane.size) P.push('_none_')
  else for (const [lane, e] of [...byLane.entries()].sort((a, b) => a[0] < b[0] ? -1 : 1)) P.push(`- \`${lane}\` — ${e.n} record(s)${e.newest ? `, newest ${e.newest}` : ''}`)
  P.push('')
  // docs map — docs/**/*.md, EXCLUDING generated views (self-reference) and the
  // session bases (a V1-shaped repo keeps session logs under docs/); links are
  // relative to the OUT file's dir (CTX-05's resolver reads them from there)
  const outDir = path.posix.dirname(outRel)
  const docs = repo.match(['docs/**/*.md'], { tracked: true })
    .filter(f => f !== outRel && !SESSION_BASES.some(b => f.startsWith(b + '/')))
    .filter(f => { const raw = repo.read(f); return raw === null || !MARKER_DETECT_RE.test(raw.split('\n', 1)[0]) })
    .sort()
  P.push(`## Docs (${docs.length})`)
  P.push('')
  if (!docs.length) P.push('_none_')
  else for (const f of docs) {
    const title = firstHeading(repo.read(f) || '') || path.posix.basename(f)
    P.push(`- [${linkTitle(title)}](${linkDest(path.posix.relative(outDir, f))})`)
  }
  P.push('')
  return P.join('\n')
}

// The claim schema's own field list, DERIVED (additionalProperties:false) — a field
// added to the schema can never silently become a "dropped unknown field" here.
// Anything outside it in a legacy entry is dropped LOUDLY, per claim.
const CLAIM_FIELDS = Object.keys(recordSchema('claim').properties).filter(k => !['record', 'id', 'slug', 'citations'].includes(k))

const GEN_USAGE = `usage: baseline gen index [--repo DIR] [--out PATH]
         baseline gen lock [--repo DIR]
         baseline gen --check [--repo DIR]
         baseline gen migrate-claims [--repo DIR]`

export function runGen(argv) {
  // help must never mutate: a generator WRITES, so an argv we don't fully
  // understand is a usage error, not a shrug-and-proceed
  if (argv.includes('--help') || argv.includes('-h')) { console.log(`baseline gen — generators that write derivable artifacts\n  ${GEN_USAGE}\n  index: write a deterministic, marker-headed index view (default docs/INDEX.md) over the records ledgers + docs map\n  lock: pin the vendored ${VENDOR_TREE}/ tree — write ${VENDOR_LOCK} ({version, tree_hash}); REC-06 flags unpinned/skewed trees\n  --check: regenerate every marker-headed view and byte-compare — the CI drift guard (zero views → trivially green; advisory job, never continue-on-error)\n  migrate-claims: explode the legacy docs/CLAIMS.json monolith into records/claims/CLM-NNNN.json (the checker reads records only since M7b; idempotent by slug)`); return 0 }
  const sub = argv[0] && !argv[0].startsWith('-') ? argv[0] : null
  const rest = sub ? argv.slice(1) : argv
  const usage = msg => { console.error(`baseline gen: ${msg}\n  ${GEN_USAGE}`); return 2 }
  const CHECK = argv.includes('--check')
  if (CHECK && sub) return usage(`--check takes no generator (it discovers marked views)`)
  const FLAGS = CHECK ? new Set(['--check', '--repo']) : sub === 'index' ? new Set(['--repo', '--out']) : new Set(['--repo'])
  const VALUELESS = new Set(['--check'])
  if (!CHECK && sub !== 'migrate-claims' && sub !== 'index' && sub !== 'lock') return usage(sub ? `unknown generator '${sub}'` : 'a generator (or --check) is required')
  for (let i = 0; i < rest.length; i++) {
    if (!rest[i].startsWith('-')) return usage(`unexpected argument '${rest[i]}'`)
    if (!FLAGS.has(rest[i])) return usage(`unknown flag '${rest[i]}'`)
    if (!VALUELESS.has(rest[i])) i++ // skip the value
  }
  const opt = makeOpt(rest)
  for (const f of ['--repo', '--out']) if (opt(f, null) === true) return usage(`${f} needs a value`)
  const REPO = path.resolve(String(opt('--repo', process.cwd())))

  if (CHECK) return runGenCheck(REPO)
  if (sub === 'lock') return runGenLock(REPO)
  if (sub === 'index') {
    // --out is repo-relative, posix, and stays INSIDE the repo — a generator that
    // can write outside its repo is a footgun, not a knob
    const rawOut = String(opt('--out', 'docs/INDEX.md'))
    const outRel = path.posix.normalize(rawOut.split(/[\\/]/).join('/'))
    if (path.posix.isAbsolute(outRel) || outRel === '..' || outRel.startsWith('../')) return usage(`--out must be a repo-relative path inside the repo (got '${rawOut}')`)
    return runGenIndex(REPO, outRel)
  }

  const repo = indexRepo(REPO)
  const { cfg } = resolveConfig(repo)
  const legacy = loadLegacyClaims(repo, cfg)
  if (!legacy.present) { console.log(`gen migrate-claims: no legacy register (${cfg.claims_file}) — nothing to migrate`); return 0 }
  if (legacy.error) { console.error(`gen migrate-claims: ${legacy.error}`); return 2 }
  if (!legacy.claims.length) { console.log(`gen migrate-claims: ${cfg.claims_file} has no claims — nothing to migrate`); return 0 }

  const existing = loadClaimRecords(repo)
  // a corrupt/partial record file hides its slug — a rerun would re-migrate its
  // claim as a duplicate while reporting success. Refuse to write until it's fixed.
  if (existing.errors.length) {
    for (const e of existing.errors) console.error(`  ✗ ${e}`)
    console.error(`gen migrate-claims: ${existing.errors.length} existing record(s) unreadable — fix or delete them, then rerun (nothing written)`)
    return 2
  }
  const migrated = new Set()
  let maxN = 0
  for (const cl of existing.claims) {
    if (cl.slug) migrated.add(String(cl.slug))
    const m = String(cl.id || '').match(/^CLM-(\d{4})$/); if (m) maxN = Math.max(maxN, parseInt(m[1], 10))
  }
  // number past every CLM-*.json on disk too, valid or not — never mint a taken id
  for (const f of repo.match(CLAIM_RECORD_GLOB)) {
    const m = f.match(/CLM-(\d{4})\.json$/); if (m) maxN = Math.max(maxN, parseInt(m[1], 10))
  }
  try { fs.mkdirSync(path.join(REPO, 'records/claims'), { recursive: true }) }
  catch (e) { console.error(`gen migrate-claims: cannot create records/claims/ — ${e.code === 'EEXIST' || e.code === 'ENOTDIR' ? 'a file exists where the directory belongs' : e.message}`); return 2 }

  let wrote = 0, skipped = 0, refused = 0
  for (const cl of legacy.claims) {
    const slug = String(cl.id ?? '')
    // the slug IS the migration key (claims.mjs shadows by it) — an unkeyed claim
    // can never be marked migrated, so writing it would duplicate on every rerun
    if (!slug) { refused++; console.error(`  ✗ (no id) refused — every legacy claim needs an "id" to key the migration: add one in ${cfg.claims_file}, rerun`); continue }
    if (migrated.has(slug)) { skipped++; console.log(`  = ${slug} already migrated — skipped`); continue }
    const rec = { record: 'claim/1', id: `CLM-${String(++maxN).padStart(4, '0')}`, slug }
    const dropped = []
    for (const k of Object.keys(cl)) if (k !== 'id' && k !== '_file' && !CLAIM_FIELDS.includes(k) && k !== 'citations') dropped.push(k)
    for (const k of CLAIM_FIELDS) if (cl[k] !== undefined) rec[k] = cl[k]
    // citations carry over losslessly or loudly: a non-array is a refusal (it was
    // already a CLAIM-04 finding — migration must not flip it to PASS by deletion),
    // and any subfield beyond url/supports_because is reported into the same
    // dropped channel as top-level fields
    if (cl.citations !== undefined) {
      if (!Array.isArray(cl.citations)) { refused++; maxN--; console.error(`  ✗ ${slug} refused — "citations" must be an array (fix in ${cfg.claims_file}, rerun)`); continue }
      const cits = []
      cl.citations.forEach((c, i) => {
        if (!c || typeof c !== 'object') { dropped.push(`citations[${i}] (not an object)`); return }
        for (const k of Object.keys(c)) if (k !== 'url' && k !== 'supports_because') dropped.push(`citations[${i}].${k}`)
        cits.push({ url: c.url, supports_because: c.supports_because })
      })
      rec.citations = cits
    }
    const errs = validateRecord('claim', rec)
    if (errs.length) {
      refused++; maxN-- // the number wasn't spent
      console.error(`  ✗ ${slug} refused (fix in ${cfg.claims_file}, rerun): ${errs.slice(0, 3).join('; ')}${errs.length > 3 ? ` (+${errs.length - 3})` : ''}`)
      continue
    }
    const rel = `records/claims/${rec.id}.json`
    const abs = path.join(REPO, rel)
    try { fs.writeFileSync(abs, JSON.stringify(rec, null, 2) + '\n', { flag: 'wx' }) }
    catch (e) { refused++; console.error(`  ✗ ${rel}: ${e.code === 'EEXIST' ? 'already exists (never overwritten)' : e.message}`); continue }
    migrated.add(slug) // a duplicate id later in the SAME monolith skips instead of minting a twin
    wrote++
    console.log(`  + ${rel} (slug: ${slug})${dropped.length ? ` — dropped: ${dropped.join(', ')}` : ''}`)
  }
  console.log(`\ngen migrate-claims: ${wrote} written · ${skipped} already migrated · ${refused} refused`)
  if (wrote) console.log(`  review + commit the new records; the checker no longer reads the legacy ${cfg.claims_file} — deleting it after review clears CLAIM-07`)
  return refused ? 1 : 0
}

// ---- gen lock (M7c) ----
function runGenLock(REPO) {
  const repo = indexRepo(REPO)
  const lock = computeVendorLock(REPO, repo)
  // asking to pin an absent tree is a failed intent, not an idempotent no-op
  // (contrast migrate-claims' "nothing to migrate": there, done IS the goal state)
  if (!lock.files && !lock.unhashable.length) { console.error(`gen lock: no vendored tree at ${VENDOR_TREE}/ — nothing to pin (the canonical vendored location; see CONTRACT.md's manual-copy procedure)`); return 1 }
  // the writer is STRICT where the verifier degrades: a tree that cannot be
  // fully read cannot be pinned honestly — refuse, naming what's in the way
  if (lock.unhashable.length) { console.error(`gen lock: ${lock.unhashable.length} entr${lock.unhashable.length === 1 ? 'y' : 'ies'} cannot be hashed — ${lock.unhashable.slice(0, 3).join(', ')}${lock.unhashable.length > 3 ? ` (+${lock.unhashable.length - 3})` : ''}; remove or fix them (symlinks and unreadable files cannot be pinned honestly)`); return 2 }
  if (typeof lock.version !== 'string') { console.error(`gen lock: ${VENDOR_TREE}/rules.json carries no readable string version — is this a baseline toolkit tree? (the lock names the version it pins, and REC-06 validates the shape it writes)`); return 2 }
  const abs = path.join(REPO, VENDOR_LOCK)
  // overwrite law, lock flavor: write over a parseable {version, tree_hash} lock
  // or into absence — a foreign file squatting the canonical path is refused,
  // same as gen index refuses a marker-less file
  let existing = null
  try { existing = fs.readFileSync(abs, 'utf8') }
  catch (e) {
    if (e.code === 'EISDIR' || e.code === 'ENOTDIR') { console.error(`gen lock: cannot write ${VENDOR_LOCK} — ${e.code === 'EISDIR' ? 'it is a directory' : 'a file exists where a directory belongs on its path'}`); return 2 }
    if (e.code !== 'ENOENT') { console.error(`gen lock: cannot read ${VENDOR_LOCK} — ${e.message}`); return 2 }
  }
  if (existing !== null) {
    let old = null
    try { old = JSON.parse(existing) } catch {}
    if (!old || typeof old !== 'object' || typeof old.version !== 'string' || typeof old.tree_hash !== 'string') {
      console.error(`gen lock: refusing to overwrite ${VENDOR_LOCK} — it exists but is not a lock ({version, tree_hash}). Move it aside.`)
      return 2
    }
  }
  const content = JSON.stringify({ version: lock.version, tree_hash: lock.tree_hash }, null, 2) + '\n'
  if (existing === content) { console.log(`gen lock: ${VENDOR_LOCK} is up to date (${lock.version} · ${lock.files} files · ${lock.tree_hash.slice(0, 12)})`); return 0 }
  try { fs.writeFileSync(abs, content) }
  catch (e) { console.error(`gen lock: cannot write ${VENDOR_LOCK} — ${e.message}`); return 2 }
  console.log(`gen lock: pinned ${VENDOR_TREE}/ — ${lock.version} · ${lock.files} files · ${lock.tree_hash.slice(0, 12)} → ${VENDOR_LOCK}; commit it (REC-06 verifies)`)
  return 0
}

// ---- gen index (M6c) ----
function runGenIndex(REPO, outRel) {
  const repo = indexRepo(REPO)
  const content = generateIndex(repo, outRel)
  const abs = path.join(REPO, outRel)
  // a symlinked out-path defeats the stay-inside-the-repo law through the string
  // guard (writes follow the link; a dangling one CREATES the outside file)
  try { if (fs.lstatSync(abs).isSymbolicLink()) { console.error(`gen index: refusing ${outRel} — it is a symlink (a generated view is a plain file inside the repo)`); return 2 } }
  catch {}
  // the overwrite law rides an UNCAPPED read: a size-capped probe would read a
  // big hand-written file as "absent" and clobber it
  let existing = null
  try { existing = fs.readFileSync(abs, 'utf8') }
  catch (e) {
    if (e.code === 'EISDIR' || e.code === 'ENOTDIR') { console.error(`gen index: cannot write ${outRel} — ${e.code === 'EISDIR' ? 'it is a directory' : 'a file exists where a directory belongs on its path'}`); return 2 }
    if (e.code !== 'ENOENT') { console.error(`gen index: cannot read ${outRel} — ${e.message}`); return 2 }
  }
  if (existing !== null && !MARKER_DETECT_RE.test(existing.split('\n', 1)[0])) {
    console.error(`gen index: refusing to overwrite ${outRel} — it exists without the generated marker (a hand-written file). Move it aside, or pass a different --out.`)
    return 2
  }
  if (existing === content) { console.log(`gen index: ${outRel} is up to date`); return 0 }
  try { fs.mkdirSync(path.dirname(abs), { recursive: true }) }
  catch (e) { console.error(`gen index: cannot create ${path.posix.dirname(outRel)}/ — ${e.code === 'EEXIST' || e.code === 'ENOTDIR' ? 'a file exists where the directory belongs' : e.message}`); return 2 }
  try { fs.writeFileSync(abs, content) }
  catch (e) { console.error(`gen index: cannot write ${outRel} — ${e.message}`); return 2 }
  console.log(`gen index: wrote ${outRel} (${content.split('\n').length} lines) — commit it; \`baseline gen --check\` guards it from drift`)
  return 0
}

// ---- gen --check (M6c) — the CI drift guard ----
function runGenCheck(REPO) {
  const repo = indexRepo(REPO)
  // discovery = tracked ∪ walked: the walk sees a just-generated, not-yet-added
  // view (the gen→check local flow must not go blind between write and git add);
  // the tracked pool sees committed views inside walk-skipped dirs (vendor/ …).
  // A vendored tree's own marked views ride along: bounded cost, and an alien
  // kind fails loudly below — documented residual.
  const pool = [...new Set([...repo.match(['**/*.md'], { tracked: true }), ...repo.match(['**/*.md'])])].sort()
  const drifted = [], broken = []
  let views = 0
  for (const f of pool) {
    // uncapped read: readText's 512KB/binary cap would silently green a big
    // drifted view — the exact silent-green hole --check exists to close
    let raw = null
    try { raw = fs.readFileSync(path.join(REPO, f), 'utf8') }
    catch (e) {
      if (e.code === 'ENOENT') {
        // deleted-but-tracked: only a red flag if the STAGED content is a view —
        // a deleted ordinary doc is git's business, not a drift finding
        const staged = repo.gitCatFile(':0', f)
        if (staged !== null && MARKER_DETECT_RE.test(staged.split('\n', 1)[0])) broken.push({ f, why: 'generated view deleted from the worktree but still tracked — restore it (regenerate) or git rm it' })
        continue
      }
      broken.push({ f, why: 'tracked but unreadable — the view (if it is one) is unscannable; fix the file or its permissions' }); continue
    }
    const m = raw.split('\n', 1)[0].match(MARKER_DETECT_RE)
    if (!m) continue
    views++
    const kind = m[1]
    if (!GEN_KINDS.has(kind)) {
      broken.push({ f, why: `unknown generated kind '${kind}' — either the vendored skill here is OLDER than the view (bump the vendored skill, then regenerate) or the marker is a typo (kinds: ${[...GEN_KINDS].join(', ')})` })
      continue
    }
    const fresh = generateIndex(repo, f)
    if (fresh !== raw) drifted.push(f)
  }
  if (!views && !broken.length) { console.log('gen --check: no generated views (marker absent) — trivially green'); return 0 }
  // repo-authored bytes (filenames, marker kind tokens) reach the terminal here —
  // the anti-tamper guard's own output must not be spoofable by the content it
  // scans (an ESC-bearing kind could overwrite a finding as green). Same sanitize
  // discipline as every other human surface.
  const S = sanitizeTTY
  for (const f of drifted) {
    console.error(`✗ ${S(f)} drifted from its inputs`)
    console.error(`    regenerate and commit: ${S(remedyCommand(REPO, 'index', f))}`)
    console.error(`    (the drift may predate this PR — regenerating here clears it for everyone; if the vendored skill just bumped, the generator's shape changed with it — regenerate with the NEW version and commit the view alongside the bump; if this file was never generated at all, someone pasted the marker — delete the marker line instead)`)
  }
  for (const b of broken) console.error(`✗ ${S(b.f)}: ${S(b.why)}`)
  if (drifted.length || broken.length) { console.error(`\ngen --check: ${drifted.length} drifted · ${broken.length} broken of ${views} view(s)`); return 1 }
  console.log(`gen --check: ${views} generated view(s) in sync`)
  return 0
}
