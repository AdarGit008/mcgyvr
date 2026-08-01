---
record: session/1
lane: <branch-name>
agent: <slug>
started: <YYYY-MM-DDTHH:MM:SSZ>
---

# Session — <lane> — <date>

<!--
Written by `baseline log -m "..." [--next "..."]` — prefer the command over this
template: it derives lane/agent/timestamp, validates against
schema/record.session.schema.json, and scrubs for secrets before the file exists.
Hand-written copies of this template are covered by the pre-push scrub hook once
it is installed (cp hooks/scrub-pre-push.sh .git/hooks/pre-push, per clone).
One session = one file at records/sessions/<lane>/<YYYY-MM-DD>-<HHMMSS>-<agent>.md
(collision-free by construction — never edit a committed record, write the next one).
-->

## Did
<what happened this session — the why, not just the what>

## Dead ends
<approaches tried and abandoned, so the next session doesn't retry them>

## Left open
next: <the single most useful next step — orient surfaces this as the lane's pause state>
