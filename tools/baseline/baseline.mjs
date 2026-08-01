#!/usr/bin/env node
// The baseline CLI — the unified entry point (V2). Routes subcommands:
//   check   score a repo against the rule set (the default; delegates to the intact
//           check.mjs, so the golden corpus and CI keep invoking check.mjs directly)
//   orient  derived-state survey for session start — lanes, backlog, divergence
//   lane    claim/reclaim a work lane — atomic ref transactions at origin (M5a/M5b)
//   log     write one scrubbed, schema-valid session record (the forensic tier)
//   jdg     author/evaluate the judgment ledger (sign-offs, deviations, break-glass)
//   gen     generators — M4c: migrate-claims (the C17 monolith explosion)
//   scrub   scan record content for secret shapes (the pre-push hook's engine)
//   help    usage
// Zero-dependency. check.mjs / rules.json / src/ are co-located — invoke by absolute path.
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { execFileSync } from 'node:child_process'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const argv = process.argv.slice(2)
// A leading non-flag token is the subcommand; a leading --flag (or nothing) means `check`,
// so `baseline --repo x` stays back-compatible with the old `check.mjs --repo x` —
// EXCEPT --help/-h, which must reach the help branch, never run a scoring check.
const cmd = (argv[0] === '--help' || argv[0] === '-h') ? 'help'
  : (argv[0] && !argv[0].startsWith('-')) ? argv[0] : 'check'
const rest = (argv[0] === cmd) ? argv.slice(1) : argv

function delegateToCheck() {
  try { execFileSync(process.execPath, [path.join(HERE, 'check.mjs'), ...rest], { stdio: 'inherit' }) }
  catch (e) { process.exit(e.status ?? 1) }
  process.exit(0)
}

if (cmd === 'check') {
  delegateToCheck()
} else if (cmd === 'admit') {
  const { runAdmit } = await import('./src/admit.mjs')
  process.exit(runAdmit(rest))
} else if (cmd === 'reconcile') {
  const { runReconcile } = await import('./src/reconcile.mjs')
  process.exit(runReconcile(rest))
} else if (cmd === 'orient') {
  const { runOrient } = await import('./src/orient.mjs')
  process.exit(await runOrient(rest))
} else if (cmd === 'lane') {
  const { runLane } = await import('./src/lane.mjs')
  process.exit(runLane(rest))
} else if (cmd === 'log') {
  const { runLog } = await import('./src/log.mjs')
  process.exit(runLog(rest))
} else if (cmd === 'jdg') {
  const { runJdg } = await import('./src/jdg.mjs')
  process.exit(runJdg(rest))
} else if (cmd === 'gen') {
  const { runGen } = await import('./src/gen.mjs')
  process.exit(runGen(rest))
} else if (cmd === 'scrub') {
  const { runScrub } = await import('./src/scrubcli.mjs')
  process.exit(runScrub(rest))
} else if (cmd === 'help' || cmd === '--help' || cmd === '-h') {
  console.log(`baseline <command> [options]

  check [--repo DIR] [--json] [--no-exec] [--profile P]   score a repo (default)
  admit [--repo DIR] [--target REF] [--json]              merge-point revalidation — a verdict is
                                                          valid only for the state it evaluated
                                                          (exit 1 = refused: stale/blocker/source-loss)
  reconcile [--repo DIR] [--json] [--dry-run]             post-merge revalidation of the default
      [--target REF]                                      branch; findings file as dedup'd issues
                                                          (exit 1 = delivery failed: tracker unreachable
                                                          or a write failed — even with zero findings)
  orient [--repo DIR] [--json] [--strict]                 derived-state survey for session start
  lane claim <issue> [--agent A]                          claim a work lane: atomic branch creation
                                                          at origin (exit 3 = already claimed)
  lane reclaim <issue|ref> [--jdg JDG-ID] [--agent A]     take over a DERIVED-ABANDONED lane (dated
                                                          takeover record; --jdg = live-takeover hatch)
  log -m "..." [--next "..."] [--lane L] [--agent A]      write a scrubbed session record
      [--from FILE] [--allow ID --allow-reason "..."]     (stdin accepted; never \$EDITOR)
  jdg new --kind K --subject S --reason "..."             record a judgment (sign-off ·
      --review-by DATE [--expect p=v] [--tripwire "..."]  deviation · risk-acceptance · break-glass)
  jdg check [--repo DIR] [--json] [--facts FILE]          evaluate the ledger: tripwires · expiry · drift
  gen index [--repo DIR] [--out PATH]                     write a deterministic, marker-headed index
  gen --check [--repo DIR]                                view (default docs/INDEX.md); --check is the
                                                          CI drift guard (zero views = trivially green)
  gen migrate-claims [--repo DIR]                         explode docs/CLAIMS.json into records/claims/
  scrub <file...> | --pushed SHA [--since SHA]            scan records for secret shapes (the pre-push
      [--allow ID --allow-reason "..."]                   hook's engine; one scan API with log/REC-02)
  help                                                    this message

  Run \`baseline\` with no command (or a leading --flag) to score, e.g. \`baseline --repo .\`.`)
  process.exit(0)
} else {
  console.error(`baseline: unknown command '${cmd}' (try: check, admit, reconcile, orient, lane, log, jdg, gen, scrub, help)`)
  process.exit(2)
}
