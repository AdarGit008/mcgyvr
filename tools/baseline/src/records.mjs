// The record kinds — one home for what the Ledger stores (plan §5): which kinds
// exist, where each lives, how each is stored (json | md-frontmatter | md-header),
// and validation against schema/record.<kind>.schema.json via the shared subset
// validator. `baseline log` writes sessions through this; M4b's jdg and M4c's
// claims/REC rules read through it.
import fs from 'node:fs'
import { validateAgainst } from './validate.mjs'
import { statusOf, FRONTMATTER_RE } from './util.mjs'

export const RECORD_KINDS = {
  session:  { schema: 'record.session.schema.json',  home: 'records/sessions/<lane>/<YYYY-MM-DD>-<HHMMSS>-<agent>.md' },
  judgment: { schema: 'record.judgment.schema.json', home: 'records/judgments/JDG-NNNN.json' },
  claim:    { schema: 'record.claim.schema.json',    home: 'records/claims/CLM-NNNN.json' },
  adr:      { schema: 'record.adr.schema.json',      home: 'records/decisions/ADR-NNNN.md' },
}

const cache = {}
export function recordSchema(kind) {
  if (!RECORD_KINDS[kind]) throw new Error(`unknown record kind '${kind}'`)
  return cache[kind] ??= JSON.parse(fs.readFileSync(new URL('../schema/' + RECORD_KINDS[kind].schema, import.meta.url), 'utf8'))
}

// -> [] when valid; error strings otherwise (the descriptor's message style).
export function validateRecord(kind, obj) {
  const errors = []
  validateAgainst(obj, recordSchema(kind), '', errors)
  return errors
}

// Flat frontmatter — '---\nkey: value\n---\n' + body. String values only (dates stay
// strings; the schemas bind shape by pattern). The boundary regex mirrors the one the
// evaluators already use, so a record the checker can read is a record this can read.
export function parseFrontmatter(md) {
  const m = String(md).match(FRONTMATTER_RE)
  if (!m) return { fields: null, body: String(md) }
  const fields = {}
  for (const line of m[1].split('\n')) {
    const kv = line.match(/^([A-Za-z_][\w-]*):\s*(.*)$/)
    if (kv) fields[kv[1]] = kv[2].trim()
  }
  return { fields, body: String(md).slice(m[0].length) }
}

export function renderFrontmatter(fields) {
  return '---\n' + Object.entries(fields).map(([k, v]) => `${k}: ${v}`).join('\n') + '\n---\n'
}

// The one spelling of a session record's path (CF1) — the writer (log) and any
// future reader derive it from here, never from a second inline template.
export function sessionRelPath(fields) {
  const stamp = `${fields.started.slice(0, 10)}-${fields.started.slice(11, 19).replace(/:/g, '')}`
  return `records/sessions/${fields.lane}/${stamp}-${fields.agent}.md`
}

// ADR header fields, statuses lowercased — the md-header storage form
// record.adr.schema.json binds. Status extraction delegates to util's statusOf,
// the SAME reader CTX-02's adr-status check uses (inline 'Status: x', '**Status**',
// and Nygard '## Status' heading forms) — one opinion about an ADR's status.
export function parseAdrHeader(md) {
  const head = String(md).split(/^##\s/m)[0]
  const grab = key => { const m = head.match(new RegExp('^' + key + '\\s*:\\s*([^\\n]+)$', 'im')); return m ? m[1].trim() : undefined }
  const fields = {}
  const status = statusOf(String(md)); if (status != null) fields.status = status.toLowerCase()
  const date = grab('Date'); if (date !== undefined) fields.date = date
  const sup = grab('Supersedes'); if (sup !== undefined) fields.supersedes = sup
  const supBy = grab('Superseded-by'); if (supBy !== undefined) fields.superseded_by = supBy
  return fields
}
