# Hooks — orientation and scrub as infrastructure

`orient-session-start.sh` runs `baseline orient` at Claude Code **SessionStart**, so every
session opens with a derived-state survey instead of reconstructing state from a status doc
(C16). It's non-fatal: orient degrades every unreachable plane to a note, and the wrapper
swallows any remaining error, so a hook can never block a session.

`scrub-pre-push.sh` is a git **pre-push** hook (M4c): it scans the `records/` content in
every outgoing range with the same scan API `baseline log` uses — deterministic secret
shapes block the push, heuristics warn. It covers hand-written records, which never met
`log`'s write-time gate; for a public repo, push is the deadline (FS4). Install per clone:

```sh
cp hooks/scrub-pre-push.sh .git/hooks/pre-push && chmod +x .git/hooks/pre-push
```

Failure modes are honest: a missing baseline runtime fails OPEN with a loud warning
(REC-02 in CI still sees what landed) — and so does a scrub **error**: exit ≥ 2 or a
crash is an environment problem, not a finding, so the hook prints a loud warning and
lets the push through; only exit 1 (real findings) blocks. A blocked push prints each
finding id, and a true false-positive is cleared with a dated judgment:
`baseline scrub --allow <finding-id> --allow-reason "..."` — commit the allowlist and
push again. `git push --no-verify` skips this hook; repos using `core.hooksPath`
(husky et al.) must install into that directory; scanning covers `records/`
(+ `.baseline/cache/` presence) in the pushed range — server-side push protection is
the layer that cannot be skipped. REC-05 PASSes on at-rest evidence of a push-time
gate: gitleaks-class config, or this hook committed into the repo's `hooks/`. GitHub
push protection satisfies the same intent but is only assertable live at M6 (its
forge rules), so at rest it alone still warns.

## Wire it into Claude Code

Add to `~/.claude/settings.json` (merge with any existing `hooks`):

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          { "type": "command", "command": "$HOME/.claude/skills/baseline/hooks/orient-session-start.sh" }
        ]
      }
    ]
  }
}
```

The command's stdout is added to the session's starting context. If you installed the skill
elsewhere, set `BASELINE_DIR` in the environment or edit the path in the script.

## Hermes

The Hermes twin ships in [`../integrations/hermes/baseline-orient/`](../integrations/hermes/baseline-orient) —
a plugin whose `on_session_start` hook + `/orient` command run `baseline orient`. (The plan's earlier
`prefetch`/`system_prompt_block` sketch was memory-provider-specific; the real session-start surface is
the `on_session_start` hook.) `SKILL.md`'s **Orientation — the first act** directive remains the
tool-agnostic fallback (C28).
