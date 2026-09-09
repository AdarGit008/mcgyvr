#!/usr/bin/env bash
# shellcheck shell=bash
# skills/mcgyvr/install.sh — put the /mcgyvr skill where a harness will find it.
#
# Two harnesses are in scope: the Claude CLI (`~/.claude/skills/`) and pi
# (`~/.pi/agent/skills/`). Both read the Agent Skills layout, so both get the
# same SKILL.md, byte for byte, from this directory. SKILL.md is generated
# (`make docs`); this script never edits it, it only copies it.
#
# Installing twice changes nothing. Uninstalling twice is not an error.
set -euo pipefail

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SKILL_MD="${HERE}/SKILL.md"

# Relative to $HOME, which is read from the environment so a test (or a user
# with a non-standard home) can point the install somewhere else.
TARGETS=(
  ".claude/skills/mcgyvr"
  ".pi/agent/skills/mcgyvr"
)

usage() {
  cat <<'USAGE'
usage: install.sh [--uninstall] [--help]

  (no args)    install the /mcgyvr skill for the Claude CLI and for pi
  --uninstall  remove it from both
USAGE
}

install_skill() {
  if [[ ! -f "${SKILL_MD}" ]]; then
    echo "install.sh: no SKILL.md next to this script (${SKILL_MD})" >&2
    exit 1
  fi
  local target dest
  for target in "${TARGETS[@]}"; do
    dest="${HOME}/${target}"
    mkdir -p -- "${dest}"
    cp -- "${SKILL_MD}" "${dest}/SKILL.md"
    echo "installed: ${dest}/SKILL.md"
  done
  echo "Invoke it with /mcgyvr; it does not load itself."
}

uninstall_skill() {
  local target dest removed=0
  for target in "${TARGETS[@]}"; do
    dest="${HOME}/${target}"
    if [[ -e "${dest}" ]]; then
      rm -rf -- "${dest}"
      echo "removed: ${dest}"
      removed=1
    else
      echo "not installed: ${dest}"
    fi
  done
  if [[ "${removed}" -eq 0 ]]; then
    echo "Nothing to remove."
  fi
}

case "${1-}" in
  "")           install_skill ;;
  --uninstall)  uninstall_skill ;;
  --help|-h)    usage ;;
  *)            usage >&2; exit 2 ;;
esac
