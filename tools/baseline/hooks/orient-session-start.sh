#!/usr/bin/env bash
# Claude Code SessionStart hook — opens every session with `baseline orient`, so
# orientation is infrastructure, not remembered discipline (C16). The survey's output is
# injected into the session's starting context.
#
# Non-fatal by construction: orient itself never hard-refuses (it degrades each unreachable
# plane to a note), and this wrapper swallows any remaining error so a hook can never block
# a session. Wire it into ~/.claude/settings.json — see hooks/README.md.
BASELINE_DIR="${BASELINE_DIR:-$HOME/.claude/skills/baseline}"
node "$BASELINE_DIR/baseline.mjs" orient --repo "${CLAUDE_PROJECT_DIR:-$PWD}" 2>/dev/null || true
