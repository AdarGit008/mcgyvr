#!/usr/bin/env bash
# shellcheck shell=bash
# skills/mcgyvr/install.sh — put the /mcgyvr and /mcgyvr-direct skills where a
# harness will find them.
#
# Two skills, each a directory of `skills/`, this one's parent: `mcgyvr` (a prompt,
# planned into contracts and run) and `mcgyvr-direct` (contracts someone wrote,
# vetted and run). Two harnesses are in scope: the Claude CLI
# (`~/.claude/skills/`) and pi (`~/.pi/agent/skills/`). Both read the Agent
# Skills layout, so each gets every skill's SKILL.md, byte for byte, in a
# directory named after the skill — and, beside a SKILL.md that has one, the
# same `references/` directory. /mcgyvr-direct's SKILL.md points at
# `references/examples.md` the way the Agent Skills layout expects,
# skill-relative, so a harness that got only SKILL.md would carry a pointer to a
# file that is not there: whoever installed the skill rather than cloning the
# repository could not reach the examples at all. All of them are generated
# (`make docs`); this script never edits one, it only copies them.
#
# SETUP.md is not copied anywhere. It is what a machine's owner reads to stand
# the ladder up, and the skills are what an agent reads to hand work over — it
# sits beside this script, and is not installed. This script's stdout is a
# list of paths, SETUP.md's among them, plus the one line naming how to obtain
# the CLI, plus the one line saying the skills do not load themselves, and never
# a file's contents: stdout is the only part of running this that can reach a
# context. The version check warns on stderr, which is not part of that promise
# and not a place a context reads.
#
# Installing twice changes nothing. Uninstalling twice is not an error.
set -euo pipefail

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

# The directory every skill is a directory of: this script's own skill's parent.
SKILLS_ROOT="$(cd -- "${HERE}/.." && pwd)"

#: The skills this script installs, each the name of its source directory
#: under SKILLS_ROOT, of the directory it lands in, and of its frontmatter
#: `name`. A skill's reference files travel with it, as the Agent Skills layout
#: places them: `<skill dir>/references/`.
SKILLS=(
  "mcgyvr"
  "mcgyvr-direct"
)

# The example contracts the CLI on PATH is asked to accept (probe_examples):
# the ones /mcgyvr-direct, the skill that teaches writing a contract, carries.
EXAMPLES_MD="${SKILLS_ROOT}/mcgyvr-direct/references/examples.md"

# Named relative to the repository, as the skill directory is: the reader is
# the person who has this checkout, and an absolute path resolved here would
# be this machine's, not theirs.
SETUP_DOC="skills/mcgyvr/SETUP.md"

# How to obtain the CLI the skill drives, as the one line on stdout that says
# it. The skill is instructions for driving `mcgyvr`; installing the
# instructions onto a machine that has no `mcgyvr` is the ordinary first case,
# and this is the command that closes it: the published package on PyPI,
# which README.md installs first. This line is the only place to change it.
CLI_INSTALL="uv tool install mcgyvr"

# The oldest `mcgyvr` this checkout can claim the skill is driving: `v0.5.0`,
# the release that renames the task types to `code`, `chat`, `agent` and
# `media`. Every release before it refuses the `task_type: code` the skill
# teaches. It is raised to the tag being cut whenever a release changes what
# the skill may write, and never sits below the latest release tag:
# tests/test_skill_packaging.py fails the suite the day a tag passes it.
#
# A floor alone cannot say whether this skill and that CLI agree — a skill
# cloned from `main` can need a CLI no release has yet — so the examples the
# skill ships are also put to the CLI (probe_examples). The floor stays for
# what the examples do not exercise, such as the verbs the skill names.
#
# It is also the floor that is safe to compare with `sort -V`, which is a
# version sort and not PEP 440: it orders `0.5.0` BEFORE `0.5.0.dev376`, where
# PEP 440 puts the dev build first (a `.devN` is a pre-release of `0.5.0`, not
# a successor to it). A `.devN` build only ever names a version ABOVE the last
# release tag, so comparing against a released tag never reaches that case.
MIN_VERSION="0.5.1"

# Where a release's skill is cloned from, by its tag, when the CLI on PATH
# refuses this checkout's skill. The same repository README.md clones.
REPO_URL="https://github.com/AdarGit008/mcgyvr"

# The checkout this script sits in, for the other fix: the CLI built from the
# same revision as the skill.
CHECKOUT="$(cd -- "${HERE}/../.." && pwd)"

# Where each harness reads skills from, relative to $HOME, which is read from
# the environment so a test (or a user with a non-standard home) can point the
# install somewhere else. A skill lands in `<harness dir>/<skill name>`.
HARNESS_DIRS=(
  ".claude/skills"
  ".pi/agent/skills"
)

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

  (no args)    install /mcgyvr and /mcgyvr-direct for the Claude CLI and for pi
  --force      overwrite an installed copy that was edited by hand
  --uninstall  remove them from both
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

# Every file the install writes for one skill, as paths relative to that
# skill's directory. SKILL.md and the reference files beside it; never SETUP.md.
payload_files() {
  local references="$1/references"
  printf 'SKILL.md\n'
  [[ -d "${references}" ]] || return 0
  local file
  for file in "${references}"/*; do
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
# reference that was renamed, dropped or moved to another skill — does not stay
# behind pretending to be part of the installed skill, and neither does the
# directory it leaves empty.
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
      if [[ "$(dirname -- "${rel}")" != "." ]]; then
        rmdir -- "$(dirname -- "${dest}/${rel}")" 2>/dev/null || true
      fi
    fi
  done <"${record}"
}

# Whether the CLI on PATH accepts every contract /mcgyvr-direct ships in
# `references/examples.md`, asked of the CLI itself: each fenced `yaml` block
# is written to a file and handed to `mcgyvr contract`. The examples are the
# schema's own shapes at this revision (docgen renders them and the suite
# validates them), so the probe needs no upkeep: whatever the skill teaches
# that this CLI refuses — a task type it does not know, a key it does not
# take — is what fails here.
#
# Returns 1 when it warned and 0 otherwise. Like the rest of check_version it
# never fails the install, and why is the same: the copy above has already
# landed, the mismatch has two fixes and only one of them is the skill, and
# the README installs the CLI first but nothing stops the skill from being
# installed before the CLI it will be paired with.
probe_examples() {
  local found="$1" examples="${EXAMPLES_MD}"
  [[ -f "${examples}" ]] || return 0
  local scratch
  scratch="$(mktemp -d 2>/dev/null)" || return 0

  local line count=0 inside=0 file=""
  while IFS= read -r line || [[ -n "${line}" ]]; do
    if [[ "${inside}" -eq 0 && "${line}" == '```yaml' ]]; then
      count=$((count + 1))
      file="${scratch}/example-${count}.yaml"
      : >"${file}"
      inside=1
    elif [[ "${inside}" -eq 1 && "${line}" == '```' ]]; then
      inside=0
    elif [[ "${inside}" -eq 1 ]]; then
      printf '%s\n' "${line}" >>"${file}"
    fi
  done <"${examples}"

  # stderr is what `mcgyvr contract` explains a refusal on; its first line
  # names the field, and the first refusal is the one quoted.
  local i why rejected=0 first=""
  for ((i = 1; i <= count; i++)); do
    if ! why="$(mcgyvr contract "${scratch}/example-${i}.yaml" 2>&1 >/dev/null)"; then
      rejected=$((rejected + 1))
      [[ -n "${first}" ]] || first="${why%%$'\n'*}"
    fi
  done
  rm -rf -- "${scratch}"
  [[ "${rejected}" -gt 0 ]] || return 0

  # A release has a tag to clone; a dev build or a bare tree does not, and a
  # tag is not invented for it.
  local fix="install the CLI from the same revision as this skill"
  if [[ -f "${CHECKOUT}/pyproject.toml" ]]; then
    fix+=": uv tool install --force ${CHECKOUT}"
  fi
  if [[ "${found}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    fix="Re-install the skills from the CLI's release (git clone --depth 1 --branch v${found} ${REPO_URL}, then its skills/mcgyvr/install.sh), or ${fix}"
  else
    fix="${fix^}"
  fi
  echo "install.sh: mcgyvr ${found} rejects ${rejected} of the ${count} example contracts /mcgyvr-direct ships (${first:-no reason given}): the skills and the CLI are from different revisions, so the skill teaches contracts this CLI refuses. ${fix}." >&2
  return 1
}

# Warns; never fails. The skill installs perfectly well on a machine that has
# no `mcgyvr` binary yet, and that machine is the ordinary case rather than a
# broken one: whoever is installing the skill is usually installing it in
# order to get started, and refusing would strand exactly that person — with
# the command that would fix it sitting one line above on stdout. So every
# case here reports and returns 0, and the install stands.
#
# Comparison is `sort -V` and not a string compare: these are PEP 440
# versions, so `0.1.10` is not `0.1.1` lexically, and the real ones carry
# `.devN` and `+local` suffixes. The `+local` part is dropped before
# comparing — it is build metadata, it orders nothing, and `+ga624cdc2` would
# otherwise be compared character by character against whatever follows the
# `+` on the other side. What remains of `sort -V`'s disagreement with PEP 440
# is the pre-release case MIN_VERSION's comment rules out.
check_version() {
  if ! command -v mcgyvr >/dev/null 2>&1; then
    echo "install.sh: no mcgyvr on PATH: the skills are installed, but there is nothing on this machine for them to drive. Get it with: ${CLI_INSTALL}" >&2
    return 0
  fi

  # `--version` prints `mcgyvr <version>` and then the config it resolved, so
  # the version is the first line's second field. The `|| reported=""` is what
  # keeps a non-zero exit from `set -e`: this is a warning, and a CLI too
  # broken to state its own version must not abort an install that succeeded.
  local reported="" found core
  reported="$(mcgyvr --version 2>/dev/null)" || reported=""
  reported="${reported%%$'\n'*}"
  found="${reported#mcgyvr }"

  if [[ -z "${found}" || "${found}" == "${reported}" ]]; then
    echo "install.sh: mcgyvr is on PATH but did not report a version; wanted ${MIN_VERSION} or newer." >&2
    return 0
  fi

  # The probe speaks first: a CLI that refuses the skill's examples is the
  # mismatch the floor below cannot see, and its fix is more exact than
  # "upgrade". One warning is enough; the floor is not then repeated.
  probe_examples "${found}" || return 0

  core="${found%%+*}"

  # What mcgyvr reports when it is importable but was never installed as a
  # package — a bare checkout on sys.path (src/mcgyvr/__init__.py). It is not
  # a version, and it is said to be one here rather than being compared as
  # `0.0.0` and reported as merely old.
  if [[ "${core}" == "0.0.0" ]]; then
    echo "install.sh: mcgyvr reports ${found}: it is running from a tree that was never installed, so it has no version to check. Install it with: ${CLI_INSTALL}" >&2
    return 0
  fi

  if [[ "$(printf '%s\n%s\n' "${MIN_VERSION}" "${core}" | sort -V | head -n 1)" != "${MIN_VERSION}" ]]; then
    echo "install.sh: mcgyvr ${found} is older than ${MIN_VERSION}, the oldest this skill is known to drive. Upgrade it with: ${CLI_INSTALL}" >&2
  fi
}

# Every target of every skill, as `<skill name> <dir under $HOME>` lines.
targets() {
  local name harness
  for name in "${SKILLS[@]}"; do
    for harness in "${HARNESS_DIRS[@]}"; do
      printf '%s %s\n' "${name}" "${harness}/${name}"
    done
  done
}

install_skill() {
  local force="$1"
  local name target dest rel src digest record from

  # Every source is verified before anything is copied, so one that fails
  # leaves every target, of every skill, as it was. A skill lands in a
  # directory named after it, and its frontmatter `name` must be that name.
  for name in "${SKILLS[@]}"; do
    from="${SKILLS_ROOT}/${name}"
    if [[ ! -f "${from}/SKILL.md" ]]; then
      echo "install.sh: no SKILL.md for the ${name} skill (${from}/SKILL.md)" >&2
      exit 1
    fi
    verify_skill "${from}/SKILL.md" "${name}"
  done

  if [[ "${force}" -eq 0 ]]; then
    while read -r name target; do
      check_installed "${HOME}/${target}"
    done < <(targets)
  fi

  while read -r name target; do
    from="${SKILLS_ROOT}/${name}"
    local -a payload=()
    while IFS= read -r rel; do
      [[ -n "${rel}" ]] && payload+=("${rel}")
    done < <(payload_files "${from}")

    dest="${HOME}/${target}"
    mkdir -p -- "${dest}"
    prune_removed "${dest}" "${payload[@]}"
    record=""
    for rel in "${payload[@]}"; do
      src="${from}/${rel}"
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
  done < <(targets)
  echo "setup: ${SETUP_DOC}"
  # The skills are instructions for driving a CLI, and this is how the CLI is
  # obtained. One line, named the same way the paths above are, and no more:
  # what to do with it once it is installed is SETUP.md's, one line up.
  echo "cli: ${CLI_INSTALL}"
  # One instruction to the operator who ran this, and the only thing that says
  # the skills do not load themselves. Not a file's contents.
  echo "Invoke them with /mcgyvr <prompt> or /mcgyvr-direct <files|dir>; neither loads itself."
  # Last, and on stderr: the install above has already succeeded, and this
  # only says whether there is anything here to drive it with.
  check_version
}

uninstall_skill() {
  local name target dest removed=0
  while read -r name target; do
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
  done < <(targets)
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
