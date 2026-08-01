#!/usr/bin/env node
// project-baseline checker — zero-dependency. Scores a repo against rules.json.
// Usage: node check.mjs [--repo <dir>] [--config <file>] [--no-exec] [--json] [--profile <name>]
// Exit code 1 if any blocker fails. See README.md.
//
// This file is the thin CLI; the runner lives in src/ (index -> config ->
// evaluators -> engine -> report). check.mjs, rules.json, and src/ are
// co-located — invoke by absolute path, never copy this file away from them.
import path from 'node:path'
import { makeOpt, makeOptAll } from './src/util.mjs'
import { loadRules } from './src/rules.mjs'
import { indexRepo } from './src/repo.mjs'
import { laneOrNull } from './src/probe.mjs'
import { resolveConfig } from './src/config.mjs'
import { CHECK_KINDS, makeEvalCheck } from './src/evaluators.mjs'
import { makeLaneWorld } from './src/facts/index.mjs'
import { runRules } from './src/engine.mjs'
import { makeColor, reportJson, reportHuman } from './src/report.mjs'
import { runSelfCheck } from './src/selfcheck.mjs'

const args = process.argv.slice(2)
const opt = makeOpt(args)
const optAll = makeOptAll(args)
// a value flag followed by another flag (or nothing) must not String(true) into a path
for (const f of ['--repo', '--config']) if (opt(f, null) === true) { console.error(`check: ${f} needs a value`); process.exit(2) }
const REPO = path.resolve(opt('--repo', process.cwd()))
const NO_EXEC = !!opt('--no-exec', false)
const JSON_OUT = !!opt('--json', false)
const SELF_CHECK = !!opt('--self-check', false)
const RULES = loadRules()
// The closed universe of project types. Every rule's applies_to must be "all" or a subset of this.
const TYPES = RULES.project_types || ['node', 'python', 'service', 'library', 'docs']

const color = makeColor(JSON_OUT)
const repo = indexRepo(REPO)
const { cfg, DEFAULTS, CLAIMS_ACTIVE, CLAIMS_REASON, ACTIVE, JDGS, DESCRIPTOR } = resolveConfig(repo, {
  cliConfigPath: opt('--config', null),
  profileArgs: optAll('--profile'),
})

if (SELF_CHECK) process.exit(runSelfCheck({ RULES, TYPES, CHECK_KINDS, DEFAULTS, color }))

// Lane identity for the M4c branch-scoped rules: lane = branch name (the FS2 seam
// log/orient already use), with detached HEAD honestly null — a CI checkout or a
// bisect is not a lane. The default branch is the descriptor's declared one only;
// undeclared stays null and the branch gate SKIPs rather than guessing 'main'.
const BRANCH = laneOrNull(repo)
const DEFAULT_BRANCH = (DESCRIPTOR.valid && DESCRIPTOR.data.ground_truth_boundary?.default_branch) || null

// The lane world (M5c): the capability-probe + forge-facts plumbing the FLOW/DIV rules
// evaluate through — LAZY (first rule that needs it pays; a single-lane or off-posture
// run never spawns gh) and exit-stable offline (degradations become labeled SKIPs).
const LANEWORLD = makeLaneWorld(repo, DESCRIPTOR)

const evalCheck = makeEvalCheck({ repo, cfg, NO_EXEC, JDGS, DESCRIPTOR, BRANCH, DEFAULT_BRANCH, LANEWORLD })
const results = runRules({ rules: RULES.rules, cfg, ACTIVE, CLAIMS_ACTIVE, CLAIMS_REASON, evalCheck, DESCRIPTOR, BRANCH, DEFAULT_BRANCH })

process.exit(JSON_OUT
  ? reportJson({ results, REPO, cfg, ACTIVE, HEAD: repo.HEAD })
  : reportHuman({ results, REPO, cfg, ACTIVE, HEAD: repo.HEAD, version: RULES.version, color }))
