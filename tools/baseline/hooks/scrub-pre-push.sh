#!/usr/bin/env bash
# baseline pre-push scrub (M4c, CF6/FS4) — for a public repo, push is the deadline:
# scan the records/ content actually being pushed with the SAME scan API `baseline log`
# uses (one opinion about what a secret looks like). Deterministic secret shapes block
# the push (exit 1); heuristics warn and never block. This is one layer of defense in
# depth (REC-05 counts gitleaks-class wiring or a committed copy of this hook as the
# at-rest evidence; server-side push protection is the layer no client can skip).
#
# Install (per clone):  cp hooks/scrub-pre-push.sh .git/hooks/pre-push && chmod +x .git/hooks/pre-push
#   (repos using core.hooksPath — husky et al. — must install into THAT directory instead)
# The runtime lookup mirrors hooks/orient-session-start.sh; override with BASELINE_DIR.
#
# Honest failure modes (documented residual risk, C34):
#   - missing runtime FAILS OPEN with a loud warning — a moved skill install must not
#     brick every push; REC-02 in CI is the backstop that still sees what landed.
#   - a scrub ERROR (exit >= 2, or a crash) also fails open, loudly — an environment
#     problem is NOT a finding, and only findings block. Exit 1 = findings = block.
#   - `git push --no-verify` skips this hook entirely; server-side push protection is
#     the layer that cannot be skipped.
BASELINE_DIR="${BASELINE_DIR:-$HOME/.claude/skills/baseline}"

if ! command -v node >/dev/null 2>&1 || [ ! -f "$BASELINE_DIR/baseline.mjs" ]; then
  echo "scrub-pre-push: baseline runtime not found (BASELINE_DIR=$BASELINE_DIR) — records NOT scanned this push" >&2
  exit 0
fi

repo_root="$(git rev-parse --show-toplevel)" || exit 0
status=0
# stdin: "<local ref> <local sha> <remote ref> <remote sha>" per ref being pushed.
# </dev/null on the scrub call: a child must never drain the remaining ref lines.
while read -r local_ref local_sha remote_ref remote_sha; do
  case "$local_sha" in *[!0]*) ;; *) continue ;; esac   # all-zero local sha = ref deletion, nothing pushed
  case "$remote_sha" in
    *[!0]*) node "$BASELINE_DIR/baseline.mjs" scrub --repo "$repo_root" --pushed "$local_sha" --since "$remote_sha" </dev/null; rc=$? ;;
    *)      node "$BASELINE_DIR/baseline.mjs" scrub --repo "$repo_root" --pushed "$local_sha" </dev/null; rc=$? ;;
  esac
  case $rc in
    0) ;;
    1) status=1 ;;
    *) echo "scrub-pre-push: scrub errored (exit $rc) — NOT a finding; failing open per the documented posture (REC-02 in CI is the backstop)" >&2 ;;
  esac
done
exit $status
