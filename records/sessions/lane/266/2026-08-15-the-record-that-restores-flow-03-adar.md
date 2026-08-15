---
record: session/5
lane: lane/266
agent: adar
started: 2026-08-15T10:30:00Z
---

# Session — lane/266 — 2026-08-15 — restoring FLOW-03

## Did

**CI's baseline job failed on FLOW-03, and it was right to.** No measurement is
affected. This record exists because the fix has to be a *new* record rather than
an edit, and because the variant that fired here is not the one already written
up.

### The mechanism, read from the rule rather than guessed

`extractNext` in `tools/baseline/src/facts/git.mjs:65-75` does not scan the file
for a `next:` line. It scans **only the `## Left open` section**, and stops at the
next heading:

```js
const start = lines.findIndex(l => /^##\s+Left open\b/i.test(l))
if (start === -1) return null
for (let i = start + 1; i < lines.length; i++) {
  if (/^##\s/.test(lines[i])) break
  const m = lines[i].match(/^\s*next:\s*(.*)$/i)
  ...
}
```

`2026-08-15-the-naming-scan-that-was-falsified-adar.md` carries a filled-in
`next:` — `#272 owns whether psi_draw still earns rig time` — but places it after
a closing `## The method note, which is the point of this record`. The loop
breaks at that heading and returns `null`, so a record with a perfectly good
next step reads as having none.

**This is a different failure from the one already on record.** Lane/231's
`2026-08-13-the-ordering-trap-in-flow-03-adar.md` documents `committedLog`
picking the lexicographically-last added record rather than the newest by time.
That is not what happened here: this lane's five records sort so that the naming
record *is* last, and it was correctly selected. The trap here is **placement
within the file**, not selection between files. Two distinct ways to fail one
rule, and the second is easier to hit, because `## Left open` reads like a
section that can appear anywhere.

### Why this is a new record and not an edit

REC-01 makes committed records append-only, and lane/113 and lane/231 both
settled the precedent in the same direction: the newest record governs, and
restructuring an older one to move its `next:` trades a true record for a green
check. The naming record's account of the falsification stands exactly as
written; this record supplies the machine-readable next step it failed to expose.

### What the rule is actually asking for

Not "a next step exists" — that is FLOW-02's territory — but *"the newest record
ends by pointing somewhere."* A record whose final section is prose rather than
`## Left open` satisfies the spirit and fails the letter, and the letter is what
CI reads. Worth knowing before writing the next one: **put `## Left open` last,
and `next:` inside it.**

## Left open

- **#272 is the gate on rig time.** #224's S1 (~2.4 h) and S2 (~4–9 h) were
  scoped to produce a `psi_draw` measurement whose premise the 2026-08-15
  re-score superseded. They should not be scheduled until #272 returns a verdict,
  and #272's first item is offline: does a pre-gate formatting pass restore any
  `pinned-pass` mass?
- **The bar decision now sits above #224's corpus work.** 50.6% of lint
  rejections lead with something `ruff format` erases, and #113 measured a
  zero-token pre-gate pass at +13.7pp. No authoring bill is real until it is
  priced.
- **FLOW-03 has two failure modes and one write-up each now.** Whether the rule
  should read the whole file rather than one section is a question for the
  baseline tool, not for this lane.

next: settle #272 on the committed re-scored rows before booking any rig time — S1/S2 stay unscheduled until it reports
