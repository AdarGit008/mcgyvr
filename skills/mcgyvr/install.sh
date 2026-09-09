#!/usr/bin/env bash
# shellcheck shell=bash
# skills/mcgyvr/install.sh — put the /mcgyvr skill where a harness will find it.
#
# Two harnesses are in scope: the Claude CLI (`~/.claude/skills/`) and pi
# (`~/.pi/agent/skills/`). Both read the Agent Skills layout, so both get the
# same SKILL.md, byte for byte, from this directory — and, beside it, the same
# `references/` directory. SKILL.md points at `references/examples.md` the way
# the Agent Skills layout expects, skill-relative, so a harness that got only
# SKILL.md would carry a pointer to a file that is not there: whoever installed
# the skill rather than cloning the repository could not reach the examples at
# all. Both are generated (`make docs`); this script never edits either, it
# only copies them.
#
# SETUP.md is not copied anywhere. It is what a machine's owner reads to stand
# the ladder up, and the skill is what an agent reads to author a contract —
# beside each other in this directory, and only one of them is installed. This
# script's stdout is a list of paths, SETUP.md's among them, plus the one line
# saying the skill does not load itself, and never a file's contents: stdout is
# the only part of running this that can reach a context.
#
# Installing twice changes nothing. Uninstalling twice is not an error.
set -euo pipefail

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SKILL_MD="${HERE}/SKILL.md"

# The reference files that travel with the skill, as the Agent Skills layout
# places them: `<skill dir>/references/`.
REFERENCES_DIR="${HERE}/references"

# Named relative to the repository, as the skill directory is: the reader is
# the person who has this checkout, and an absolute path resolved here would
# be this machine's, not theirs.
SETUP_DOC="skills/mcgyvr/SETUP.md"

# Relative to $HOME, which is read from the environment so a test (or a user
# with a non-standard home) can point the install somewhere else.
TARGETS=(
  ".claude/skills/mcgyvr"
  ".pi/agent/skills/mcgyvr"
)

#: The directory name every target ends in, which the frontmatter `name` must
#: match. Checked against each target before the source is verified against it.
SKILL_NAME="mcgyvr"

# Beside each installed copy, the digest of every file this script wrote
# there, one `digest  path` line each. It is what tells a copy somebody edited
# by hand from a copy this script put there and has since been regenerated:
# the first differs from the record and is refused, the second matches it and
# is overwritten. Without the record there is only "installed differs from
# source", which is equally true of the ordinary upgrade — and refusing that
# would strand every machine on the SKILL.md it already has.
RECORD=".mcgyvr-installed"

#: The frontmatter bound both harnesses hold a description to.
DESCRIPTION_MAX=1024

usage() {
  cat <<'USAGE'
usage: install.sh [--force] [--uninstall] [--help]

  (no args)    install the /mcgyvr skill for the Claude CLI and for pi
  --force      overwrite an installed copy that was edited by hand
  --uninstall  remove it from both
USAGE
}

digest_of() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum -- "$1" | cut -d ' ' -f 1
  else
    shasum -a 256 -- "$1" | cut -d ' ' -f 1
  fi
}

trim() {
  local s="$1"
  s="${s#"${s%%[![:space:]]*}"}"
  s="${s%"${s##*[![:space:]]}"}"
  printf '%s' "${s}"
}

unquote() {
  local s="$1"
  case "${s}" in
    '"'*'"') s="${s:1:${#s}-2}" ;;
    "'"*"'") s="${s:1:${#s}-2}" ;;
  esac
  printf '%s' "${s}"
}

# The source, checked once before anything is copied. Checking the file after
# it landed reads the bytes a harness will load, but it reads them too late:
# a SKILL.md that fails leaves a corrupt copy installed and no record beside
# it, and a missing record is exactly what the next run reads as "installed
# before this script kept one" and overwrites without asking. Verifying the
# source first is what makes the comment on check_installed true — a refusal
# leaves every target as it was. That the bytes which landed are these bytes
# is then a digest comparison, made in the copy loop.
verify_skill() {
  local file="$1" expected_name="$2"
  local -a lines=()
  mapfile -t lines <"${file}"

  if [[ "${#lines[@]}" -eq 0 || "$(trim "${lines[0]}")" != "---" ]]; then
    echo "install.sh: ${file}: frontmatter must open the file" >&2
    return 1
  fi
  local i end=-1
  for ((i = 1; i < ${#lines[@]}; i++)); do
    if [[ "$(trim "${lines[i]}")" == "---" ]]; then
      end="${i}"
      break
    fi
  done
  if [[ "${end}" -lt 0 ]]; then
    echo "install.sh: ${file}: frontmatter is not closed by a second ---" >&2
    return 1
  fi

  local name="" description=""
  for ((i = 1; i < end; i++)); do
    case "${lines[i]}" in
      name:*) name="$(unquote "$(trim "${lines[i]#name:}")")" ;;
      description:*) description="$(unquote "$(trim "${lines[i]#description:}")")" ;;
    esac
  done

  if [[ "${name}" != "${expected_name}" ]]; then
    echo "install.sh: ${file}: frontmatter name '${name}' is not the directory it lands in ('${expected_name}')" >&2
    return 1
  fi
  if [[ -z "${description}" ]]; then
    echo "install.sh: ${file}: frontmatter has no description" >&2
    return 1
  fi
  if [[ "${#description}" -gt "${DESCRIPTION_MAX}" ]]; then
    echo "install.sh: ${file}: description is ${#description} characters, over the ${DESCRIPTION_MAX} a harness will read" >&2
    return 1
  fi
}

# Every file the install writes, as paths relative to this directory. SKILL.md
# and the reference files beside it; never SETUP.md.
payload_files() {
  printf 'SKILL.md\n'
  [[ -d "${REFERENCES_DIR}" ]] || return 0
  local file
  for file in "${REFERENCES_DIR}"/*; do
    [[ -f "${file}" ]] || continue
    printf 'references/%s\n' "$(basename -- "${file}")"
  done
}

# Asked of every target before any of them is written, so a refusal leaves all
# of them as they were rather than half of them upgraded. Every file named in
# the record is checked, the reference files among them.
check_installed() {
  local dest="$1"
  local record="${dest}/${RECORD}"
  # No record: installed before this script kept one, and carrying whatever
  # SKILL.md that was. A hand edit and the copy this script wrote are
  # indistinguishable there, and the one that must not be refused is the
  # upgrade — so nothing is refused.
  [[ -f "${record}" ]] || return 0
  local was rel file now
  while read -r was rel; do
    [[ -n "${was}" ]] || continue
    # A record written before this script listed paths carries one bare
    # digest, and it is SKILL.md's.
    [[ -n "${rel}" ]] || rel="SKILL.md"
    file="${dest}/${rel}"
    [[ -f "${file}" ]] || continue
    now="$(digest_of "${file}")"
    if [[ "${was}" != "${now}" ]]; then
      echo "install.sh: ${file} differs from the copy this script installed; something has edited it. Re-run with --force to overwrite it." >&2
      return 1
    fi
  done <"${record}"
}

# A file this script installed earlier that the skill no longer carries — a
# reference that was renamed or dropped — does not stay behind pretending to
# be part of the installed skill.
prune_removed() {
  local dest="$1"
  shift
  local record="${dest}/${RECORD}"
  [[ -f "${record}" ]] || return 0
  local was rel keep found
  while read -r was rel; do
    [[ -n "${rel}" ]] || continue
    found=0
    for keep in "$@"; do
      if [[ "${keep}" == "${rel}" ]]; then
        found=1
        break
      fi
    done
    if [[ "${found}" -eq 0 && -f "${dest}/${rel}" ]]; then
      rm -f -- "${dest}/${rel}"
      echo "removed: ${dest}/${rel}"
    fi
  done <"${record}"
}

install_skill() {
  local force="$1"
  if [[ ! -f "${SKILL_MD}" ]]; then
    echo "install.sh: no SKILL.md next to this script (${SKILL_MD})" >&2
    exit 1
  fi

  local target dest rel src digest record
  # Verifying the source once is only sound if every target expects the same
  # frontmatter name.
  for target in "${TARGETS[@]}"; do
    if [[ "$(basename -- "${target}")" != "${SKILL_NAME}" ]]; then
      echo "install.sh: ${target}: every target must be a directory named '${SKILL_NAME}'" >&2
      exit 1
    fi
  done
  verify_skill "${SKILL_MD}" "${SKILL_NAME}"

  local -a payload=()
  while IFS= read -r rel; do
    [[ -n "${rel}" ]] && payload+=("${rel}")
  done < <(payload_files)

  if [[ "${force}" -eq 0 ]]; then
    for target in "${TARGETS[@]}"; do
      check_installed "${HOME}/${target}"
    done
  fi

  for target in "${TARGETS[@]}"; do
    dest="${HOME}/${target}"
    mkdir -p -- "${dest}"
    prune_removed "${dest}" "${payload[@]}"
    record=""
    for rel in "${payload[@]}"; do
      src="${HERE}/${rel}"
      mkdir -p -- "$(dirname -- "${dest}/${rel}")"
      cp -- "${src}" "${dest}/${rel}"
      digest="$(digest_of "${dest}/${rel}")"
      if [[ "${digest}" != "$(digest_of "${src}")" ]]; then
        echo "install.sh: ${dest}/${rel}: what landed is not what was copied" >&2
        exit 1
      fi
      record+="${digest}  ${rel}"$'\n'
      echo "installed: ${dest}/${rel}"
    done
    printf '%s' "${record}" >"${dest}/${RECORD}"
  done
  echo "setup: ${SETUP_DOC}"
  # One instruction to the operator who ran this, and the only thing that says
  # the skill does not load itself. Not a file's contents.
  echo "Invoke it with /mcgyvr; it does not load itself."
}

uninstall_skill() {
  local target dest removed=0
  for target in "${TARGETS[@]}"; do
    dest="${HOME}/${target}"
    if [[ -e "${dest}" ]]; then
      # The whole skill directory: SKILL.md, the reference files beside it,
      # and the record that named them.
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
  "")           install_skill 0 ;;
  --force)      install_skill 1 ;;
  --uninstall)  uninstall_skill ;;
  --help|-h)    usage ;;
  # One line, and it names the document rather than growing a section per
  # harness: two harnesses are in scope, anything else is a machine whose
  # owner has to read the setup document anyway.
  *)            echo "install.sh: ${1}: not an argument this understands — ${SETUP_DOC}" >&2; exit 2 ;;
esac
