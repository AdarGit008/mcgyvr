"""Render the documents that are generated from mcgyvr's schemas.

`render_reference` and `render_setup` project the config `SCHEMA` into the
configuration reference and SETUP.md. Two skills are rendered, and setup is not
part of either: `render_skill` is /mcgyvr, a prompt handed to `mcgyvr "<prompt>"`
and nothing about writing a contract; `render_direct_skill` is /mcgyvr-direct,
contracts someone wrote handed to `mcgyvr direct`, one instruction generated from
the contract schema, carrying the failure-notes record's fields from
`mcgyvr.notes`. Both take their flags and exit codes from the CLI's own parser.
`render_examples` and `render_notes_schema` write /mcgyvr-direct's
`references/`. `main` renders the reference to a temporary file, checks it and
deletes it, then writes the other five — or, with `--check`, reports the ones
that are out of date without touching them.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import textwrap
from collections.abc import Sequence
from pathlib import Path

from mcgyvr.catalog import catalog

from . import contract as contract_schema
from . import notes as failure_notes
from .config import (
    FLEET_FILENAME,
    JOURNAL_DIR_DEFAULT,
    KNOBS,
    LAUNCHER_NATIVE,
    POLICY_FILENAME,
    RELIEF_FILENAME,
    SCHEMA,
    SWITCHES,
    USE_CASES,
    Field,
)
from .fleet import roots
from .hostos import CACHE_FOLDERS, DATA_FOLDERS, PATH_EXPORT, PATH_POWERSHELL

# First line of every document generated from the config schema: the note that
# it is generated, which source it comes from, and the command that redraws it.
MARKER = (
    "<!-- Code generated from src/mcgyvr/config.py by `make docs`. DO NOT EDIT. -->"
)

# The checkout root, taken from this file's location (src/mcgyvr/docgen.py is
# two parents down), and the skill documents' paths inside it: where `main` writes
# and checks them unless an output flag names somewhere else.
REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = Path("skills/mcgyvr/SKILL.md")
DIRECT_SKILL_PATH = Path("skills/mcgyvr-direct/SKILL.md")
SETUP_PATH = Path("skills/mcgyvr/SETUP.md")
EXAMPLES_PATH = Path("skills/mcgyvr-direct/references/examples.md")
NOTES_SCHEMA_PATH = Path("skills/mcgyvr-direct/references/failure-notes.schema.json")
SKILL_MARKER = (
    "<!-- Code generated from src/mcgyvr/contract.py and src/mcgyvr/docgen.py by "
    "`make docs`. DO NOT EDIT. -->"
)
PROMPT_SKILL_MARKER = (
    "<!-- Code generated from src/mcgyvr/flagset.py and src/mcgyvr/docgen.py by "
    "`make docs`. DO NOT EDIT. -->"
)

#: The longest line a generated skill holds: its prose, records and lists are
#: wrapped to it (the front matter's one-line description is the exception).
WIDTH = 105

# The "Value types" table of both generated documents: for each type name a
# reader sees in a Type column, the rule the loader enforces on it, phrased for
# someone writing the config rather than for someone reading the validator.
_TYPES: tuple[tuple[str, str], ...] = (
    (
        "number",
        "A whole number. `true` is not a number, even though Python says it is.",
    ),
    (
        "text",
        "A non-empty string. An empty value is rejected rather than treated as "
        "unset — remove the key instead.",
    ),
    (
        "URL",
        "Text that carries a scheme: it must start with `http://` or `https://`.",
    ),
    ("boolean", "`true` or `false`, unquoted."),
    (
        "decimal number",
        "A number that may carry a fraction.",
    ),
    (
        "one of ...",
        "Text drawn from a fixed set. Anything else is rejected, with the valid "
        "values named.",
    ),
    (
        "env var name",
        "The **name** of an environment variable (e.g. `ANTHROPIC_API_KEY`), "
        "never the value. Credentials are never written into this file; "
        "mcgyvr resolves the name at point of use and a task sandbox "
        "never sees the result.",
    ),
    ("list of text", "A YAML list of non-empty strings."),
    (
        "block",
        "A nested mapping with a fixed set of keys, documented in its own section.",
    ),
    (
        "block map",
        "A mapping whose keys you choose; every entry takes the same fixed set "
        "of keys.",
    ),
    (
        "free-form block",
        "A nested mapping whose keys the schema does not fix.",
    ),
    (
        "map of numbers",
        "A mapping from names you choose to whole numbers.",
    ),
)

_KIND_LABELS: dict[str, str] = {
    "int": "number",
    "float": "decimal number",
    "str": "text",
    "url": "URL",
    "bool": "boolean",
    "env_name": "env var name",
    "str_list": "list of text",
    "glob_list": "list of globs",
    "mapping": "free-form block",
    "int_map": "map of numbers",
    "block": "block",
    "block_map": "block map",
    "block_list": "list of blocks",
}


def _escape(text: str) -> str:
    """Escape a pipe, so the text cannot split the Markdown table cell it is in."""
    return text.replace("|", "\\|")


def _type_label(field: Field) -> str:
    if field.kind == "enum":
        return "one of " + ", ".join(f"`{c}`" for c in field.valid_choices())
    label = _KIND_LABELS[field.kind]
    # A numeric field's declared bounds are part of its type as a reader sees it:
    # "number (min 1)" says more than "number". A field with neither bound keeps the
    # bare label.
    bounds = []
    if field.min_value is not None:
        bounds.append(f"min {field.min_value}")
    if field.max_value is not None:
        bounds.append(f"max {field.max_value}")
    if bounds:
        return f"{label} ({', '.join(bounds)})"
    return label


def _default_label(field: Field) -> str:
    """Return the Default cell the reference should show for a field.

    A required field, and a block of any shape, shows an em dash rather than a
    value; a list shows `[]` when empty and its contents otherwise; a boolean is
    lowercased so it reads as YAML; a field with no default at all shows
    `unset`.
    """
    if field.required:
        return "—"
    if field.kind in ("block", "block_map", "block_list", "mapping", "int_map"):
        return "—"
    if field.kind == "str_list":
        return "`[]`" if not field.default else f"`{list(field.default)}`"
    if field.default is None:
        return "unset"
    if field.kind == "bool":
        return f"`{str(field.default).lower()}`"
    return f"`{field.default}`"


def _describe(field: Field) -> str:
    """Return the Description cell: the field's doc, plus how to bind it.

    A field carrying a `bind_hint` gets it appended as a sentence, because the
    hint is what to write for a key the config may leave out. The whole cell is
    escaped for its table row.
    """
    text = field.doc
    if field.bind_hint:
        text = f"{text} To bind it: {field.bind_hint}."
    return _escape(text)


def _table(fields: Sequence[Field], prefix: str) -> list[str]:
    lines = [
        "| Key | Type | Required | Default | Description |",
        "| --- | --- | --- | --- | --- |",
    ]
    for field in fields:
        name = f"{prefix}{field.name}" if prefix else field.name
        required = "**yes**" if field.required else "no"
        lines.append(
            f"| `{name}` | {_type_label(field)} | {required} | "
            f"{_default_label(field)} | {_describe(field)} |"
        )
    lines.append("")
    return lines


def _section(field: Field, path: str, level: int, dotted: bool = False) -> list[str]:
    """Render one block field as a section, heading included.

    The body is the field's own doc, a line saying what each entry is when the
    field is a map or a list of blocks, a table of the block's keys, and a
    section one level deeper for every inner field that has keys of its own.
    With `dotted` each inner table key is written as its full dotted path;
    without it, keys are named as they appear inside the block.
    """
    heading = "#" * level
    lines = [f"{heading} `{path}`", "", _escape(field.doc), ""]

    if field.kind == "block_map":
        lines += ["Each entry takes these keys:", ""]
    elif field.kind == "block_list":
        lines += ["An ordered list; each entry takes these keys:", ""]

    lines += _table(field.block, f"{path}." if dotted else "")

    for inner in field.block:
        if inner.block:
            lines += _section(inner, f"{path}.{inner.name}", level + 1, dotted)
    return lines


def render_reference() -> str:
    """Render the configuration reference from the config `SCHEMA`.

    The marker, the prose about how the loader behaves, and the value-type table
    are fixed; the top-level key table and a section per block are projections of
    `SCHEMA`, so a key that is documented and a key that is validated cannot
    disagree.
    """
    lines = [
        MARKER,
        "",
        "# Configuration reference",
        "",
        f"Every key `{FLEET_FILENAME}`, `{POLICY_FILENAME}` and "
        f"`{RELIEF_FILENAME}` accept.",
        "",
        "This page is generated from `SCHEMA` in `src/mcgyvr/config.py` — the same",
        "declaration the loader validates against. It is not a description of the",
        "config format kept alongside one; it is a projection of it, so a documented",
        "key and a validated key cannot disagree.",
        "",
        "Three properties hold across every key here, because the loader enforces",
        "them rather than documenting them and hoping:",
        "",
        "- **Unknown keys fail.** A typo'd key that is ignored is a config that",
        "  silently does something other than what it says.",
        "- **No silent defaults for things that must be bound.** A default ships only",
        "  when it is a real working value. Anything else is absent, and its absence",
        "  surfaces at the point of use naming the key and how to bind it.",
        "- **Credentials are never values.** Keys that would hold a secret take the",
        "  *name* of an environment variable. Writing a key in directly is rejected",
        "  by name, not with a generic error.",
        "",
        "## Value types",
        "",
        "| Type | Accepted |",
        "| --- | --- |",
    ]
    for name, rule in _TYPES:
        lines.append(f"| {name} | {_escape(rule)} |")
    lines += ["", "## Top-level keys", ""]
    lines += _table(SCHEMA, "")

    for field in SCHEMA:
        if field.block:
            lines += _section(field, field.name, 2)

    return "\n".join(lines).rstrip("\n") + "\n"


# SETUP.md alone: the constants its prose and its notes are built from.

#: The three keys SETUP.md lists as the levers, whose effect `mcgyvr local_pool`
#: prints. Each bullet's text is the key's own schema doc, so the list cannot
#: drift from the field it describes; a name here that `SCHEMA` does not declare
#: raises `KeyError` at render time instead of printing a bullet with nothing
#: after it.
_LEVERS: tuple[str, ...] = ("units", "ladder", "max_escalations")


#: The launchd label the macOS login note names, and its plist's file name.
_LAUNCHD_LABEL = "mcgyvr-rig"
#: The least time launchd leaves between two starts of that agent, in seconds
#: (launchd.plist's ThrottleInterval), so a rig that refuses at once is not
#: restarted in a tight loop.
_LAUNCHD_THROTTLE_S = 60
#: How SETUP.md and the README install the skills on Windows: the PowerShell
#: every Windows has, for this one run, with no profile; a policy that
#: refuses every script is lifted for the run only, the downloaded-file check
#: kept.
INSTALL_PS1_COMMAND = (
    "powershell -NoProfile -ExecutionPolicy RemoteSigned -File "
    "mcgyvr\\skills\\mcgyvr\\install.ps1"
)
#: The file the Windows login note puts in the user's Startup folder.
_STARTUP_FILE = "mcgyvr-rig.cmd"


#: The serving and rig names *macOS and Windows* states. docgen sits above
#: the serving seam and imports neither `mcgyvr.serving` nor `mcgyvr.rig`, so
#: they are written here once, and
#: tests/test_the_setup_document_speaks_macos_and_windows.py holds each to
#: the constant that defines it (`llamacpp.TAG`/`BACKENDS`, `native.BIN`,
#: `NVIDIA_SMI_EXE`, `BACKEND_ENV`, `fetcher.WEIGHTS_DIR_ENV`,
#: `gatelib.LOCAL_TRANSPORT_ENV`/`SSHD`, `release.QUARANTINE`,
#: `rungs.KEY_ENV`): a rename there fails the suite until this follows.
NATIVE_TAG = "b11960"
NATIVE_BACKENDS = ("metal", "cuda", "vulkan", "cpu")
NATIVE_BIN = "bin/llama.cpp"
NATIVE_BACKEND_ENV = "MCGYVR_NATIVE_BACKEND"
NVIDIA_SMI_EXE = "nvidia-smi.exe"
WEIGHTS_DIR_ENV = "MCGYVR_WEIGHTS"
LOCAL_TRANSPORT_ENV = "MCGYVR_LOCAL_TRANSPORT"
SSHD_PORT = 22
QUARANTINE = "com.apple.quarantine"
HUB_KEY_ENV = "MCGYVR_HUB_API_KEY"


def _macos_windows_section() -> list[str]:
    """SETUP.md's *macOS and Windows*: what differs there, and nothing else.

    Names from the core (folders, the launcher, the journal default, the
    PATH lines) come from their modules; the serving and rig names come from
    the constants above, each held to its module by a test. The commands are
    ones a person runs; mcgyvr installs no service.
    """
    tag = NATIVE_TAG
    metal, cuda, vulkan, cpu = NATIVE_BACKENDS
    plist = f"~/Library/LaunchAgents/{_LAUNCHD_LABEL}.plist"
    startup = f"\"$([Environment]::GetFolderPath('Startup'))\\{_STARTUP_FILE}\""
    home = roots.HOME_DIR

    def para(text: str) -> list[str]:
        return [*_wrap(text, rest=""), ""]

    def folders(name: str, shown: Sequence[tuple[str, str]]) -> list[str]:
        where = "; ".join(f"`{folder}` on {system}" for system, folder in shown)
        return _wrap(f"{name}: {where}.", first="- ", rest="  ")

    return [
        "## macOS and Windows",
        "",
        *para(
            "mcgyvr runs on macOS and Windows as it does on Linux; this is what "
            "differs. `~` is your home folder (`%USERPROFILE%` on Windows)."
        ),
        *para(
            "**Install.** `uv tool install mcgyvr` puts the CLI in `~/.local/bin` "
            "on every system. On Windows the skills install with "
            "`skills/mcgyvr/install.ps1`, the twin of `install.sh`: the same "
            "skills, into the same folders under `~` (`.claude/skills`, "
            "`.pi/agent/skills`). `-ExecutionPolicy RemoteSigned` lets that one "
            "run go ahead where PowerShell's policy refuses every script, and "
            "changes no setting; a script from `git clone` carries no "
            "downloaded-file mark, so it runs (one taken from a zip a browser "
            "downloaded needs `Unblock-File` first):"
        ),
        "```",
        INSTALL_PS1_COMMAND,
        "```",
        "",
        "**Folders.** Each system's own, by default:",
        "",
        *folders(f"data (`${roots.DATA_ENV}`)", DATA_FOLDERS),
        *folders("caches (the model index, the weights)", CACHE_FOLDERS),
        f"- config (`${roots.HOME_ENV}`): `{home}` on every system.",
        "",
        *para(
            "`$XDG_STATE_HOME` and `$XDG_CACHE_HOME` still win when set (the "
            f"weights follow `${WEIGHTS_DIR_ENV}` alone), and `journal.dir` "
            f"defaults to `{JOURNAL_DIR_DEFAULT}` everywhere. Windows checks no "
            "file owner or mode: a file is as private as its folder, and these "
            "folders are in your own profile. A folder named by "
            f"`${roots.HOME_ENV}`, `${roots.DATA_ENV}` or an XDG variable keeps "
            "whatever ACL it has, so keep the rig token's folder "
            f"(`${roots.HOME_ENV}`) inside your profile."
        ),
        *para(
            "**Serving, with no Docker.** On a Mac or a Windows machine, `mcgyvr "
            f"setup` writes `launcher: {LAUNCHER_NATIVE}` for a llama.cpp unit on "
            "the machine it runs on. Its first start fetches the llama.cpp build "
            f"mcgyvr pins (`{tag}`, the same build as the Linux image) into "
            f"`{NATIVE_BIN}/{tag}/` under `{home}`, checks it "
            "against its pinned sha256, and keeps the server up with mcgyvr's "
            f"own supervisor. The build is `{metal}` on Apple silicon; on Windows "
            f"`{cuda}` where `{NVIDIA_SMI_EXE}` reads a driver a pinned "
            "CUDA build runs (found by full path only: an absolute folder on "
            "PATH, `System32` or the NVIDIA `NVSMI` folder, never by bare name), "
            f"else `{vulkan}` where a Vulkan loader is installed, else `{cpu}`; "
            f"`${NATIVE_BACKEND_ENV}` names one instead. vLLM units run only on "
            "Linux, in containers, and remote rigs are Linux machines read over "
            "ssh. This machine is reached without ssh: always on macOS and "
            f"Windows, and on Linux when no sshd answers on port {SSHD_PORT} "
            f"(`${LOCAL_TRANSPORT_ENV}`, `direct` or `ssh`, decides instead). A "
            "native unit has no sleep route, so `mcgyvr serve sleep` and `wake` "
            "refuse it."
        ),
        *para(
            "**Firewall and quarantine.** A native server listens on 127.0.0.1 "
            "alone (a unit stating another address is refused) and takes no "
            "connection from the network, so neither the macOS nor the Windows "
            "firewall is expected to ask about it. On macOS a unit the hub uses "
            "is reached through the rig agent, which relays to that address "
            "over its own outgoing connection; on Windows a native unit serves "
            "this machine, since the rig agent does not run there yet (below). "
            f"On macOS the fetch removes the `{QUARANTINE}` flag from the build "
            "after its sha256 check, so Gatekeeper does not stop it at first "
            "start."
        ),
        *para(
            "**Long paths (Windows).** Windows limits a path to 260 characters "
            "(`MAX_PATH`). The weights land under their own file names in the "
            "cache folder, well inside that; if a path of yours still passes "
            f"it, point `${WEIGHTS_DIR_ENV}` at a short folder. Windows' "
            "`LongPathsEnabled` key lifts the limit only for programs that "
            "declare long paths (Python does; the llama.cpp build is not known "
            "to), and is set from a PowerShell run as administrator "
            "(Microsoft's command, from *Maximum Path Length Limitation*):"
        ),
        "```",
        "New-ItemProperty -Path "
        '"HKLM:\\SYSTEM\\CurrentControlSet\\Control\\FileSystem" `',
        '  -Name "LongPathsEnabled" -Value 1 -PropertyType DWORD -Force',
        "```",
        "",
        *para(
            "**Starting at login.** mcgyvr installs no service. A rig lending to "
            "a hub runs `mcgyvr rig run` in a terminal; to start it at login "
            "instead, once `mcgyvr rig join` has kept its token (`mcgyvr rig "
            "status` says so), run these yourself. On macOS, a launchd user "
            "agent that starts at login and again after an exit with an error, "
            "at most once a minute. On macOS today the agent relays to this "
            "machine's units; it lends no unified GPU yet and offers peers no "
            "LAN address:"
        ),
        "```sh",
        "mkdir -p ~/Library/LaunchAgents ~/Library/Logs",
        f"cat > {plist} <<EOF",
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<plist version="1.0"><dict>',
        f"  <key>Label</key><string>{_LAUNCHD_LABEL}</string>",
        "  <key>ProgramArguments</key><array>",
        "    <string>$HOME/.local/bin/mcgyvr</string>",
        "    <string>rig</string><string>run</string>",
        "  </array>",
        "  <key>RunAtLoad</key><true/>",
        "  <key>KeepAlive</key><dict><key>SuccessfulExit</key><false/></dict>",
        f"  <key>ThrottleInterval</key><integer>{_LAUNCHD_THROTTLE_S}</integer>",
        "  <key>StandardErrorPath</key>"
        "<string>$HOME/Library/Logs/mcgyvr-rig.log</string>",
        "</dict></plist>",
        "EOF",
        f"launchctl bootstrap gui/$(id -u) {plist}",
        "```",
        "",
        *para(
            f"`launchctl bootout gui/$(id -u)/{_LAUNCHD_LABEL}` stops it until "
            "the next login or `bootstrap` (after editing the plist, `bootout` "
            "first, then `bootstrap` again); delete the plist to drop it. "
            "launchd starts it without your shell's variables, so a variable the "
            f"agent reads (`${HUB_KEY_ENV}`) set in `~/.zshrc` is not seen there."
        ),
        *para(
            "On Windows, `mcgyvr rig run` does not start yet (its pooled-session "
            "code imports a module Windows lacks, `fcntl`). When it does, a line "
            "in your Startup folder starts it at your login with no "
            "administrator (a `schtasks /sc onlogon` task runs at any user's "
            "logon and is created from an elevated prompt). From PowerShell, "
            "and `Remove-Item` on the same path to drop it:"
        ),
        "```powershell",
        f"Set-Content -LiteralPath {startup} `",
        '  -Value \'@start "" /min "%USERPROFILE%\\.local\\bin\\mcgyvr.exe" rig run\'',
        "```",
        "",
    ]


def render_setup() -> str:
    """Render SETUP.md: how a machine comes to have a config, and what it says.

    The prose is fixed; the value types, the top-level key table and one section
    per block are rendered from `SCHEMA`, with inner keys named by full path.
    """
    by_name = {field.name: field for field in SCHEMA}
    lines = [
        MARKER,
        "",
        "# Setting up mcgyvr",
        "",
        "First run, once per machine. Nothing here is read to author a contract;",
        f"this is how `{FLEET_FILENAME}` and `{POLICY_FILENAME}` come to exist "
        f"and what they can say.",
        "",
        "```",
        "mcgyvr setup",
        "mcgyvr local_pool",
        "```",
        "",
        "`mcgyvr setup` reads each rig once and stages a setup bound to what it",
        "serves in a folder of the run's own, `$MCGYVR_DATA/setup/<run>/` (default",
        "`~/.local/state/mcgyvr/setup/<run>/` on Linux; *macOS and Windows*",
        "below names the data folder there), kept as the record of that run; it",
        "writes nothing in the working directory. It prints what was decided and",
        "why, then what is *not* configured and what that costs.",
        "",
        "Run at a terminal with no flags, it asks which rigs serve — `local`,",
        "`remote` or `both` (Enter is `local`) — and, for `remote` or `both`,",
        "the ssh host(s) to read. It then asks the use case by letter or name",
        "(`[m] mcgyvr-code`, `[k] code`, `[c] chat`, `[a] agent`; there is no",
        "Enter default) and, for `mcgyvr-code` only, whether to dedicate a unit",
        "to Jev (Enter is no): the",
        "questions `--use-case` and `--jev` answer. It plans a",
        "model of that use case for each rig, says whether its candidates came",
        "from the Hugging Face Hub, the cache of an earlier Hub read or the",
        "shipped catalog, asks before each download, writes the staged setup",
        "once and emits its launch specs once, and asks before it starts the",
        "serving containers (on this Mac or Windows machine, native servers:",
        "*macOS and Windows* below) through the door. It then samples the",
        "fleet: a read of every rig, a",
        "probe and a load of every unit, the use case's sample task (for",
        "`mcgyvr-code`, a one-function bug fix the deterministic gate must pass;",
        "for `code` and `chat`, one word from each unit) and",
        "a Jev unit's one typed choice. A green sample is stamped, and on",
        "`Lock the fleet and name it live? [y/N]` it is locked, promoted and",
        "named live. A red sample is never locked; its reasons are printed.",
        "",
        "When the interactive setup finishes, it offers to put `~/.local/bin`,",
        "where `uv tool install` puts `mcgyvr`, on PATH, once you say yes. A",
        f"shell's rc file gets `{PATH_EXPORT}`",
        "(`~/.bashrc`, `~/.zshrc`, `~/.profile`, or",
        "`~/.config/fish/config.fish`, by `$SHELL`; `~/.zshrc` on macOS when",
        "`$SHELL` is unset). On Windows the PowerShell profile gets",
        f"`{PATH_POWERSHELL}`:",
        "the profile PowerShell itself names (PowerShell 7's when it is",
        "installed, else Windows PowerShell's, each run by its full path).",
        "Where PowerShell's execution policy runs no profile (`Restricted`,",
        "a Windows client's when none is set, or `AllSigned`), setup writes",
        "none and names `uv tool update-shell`, uv's own way to put the folder",
        "on PATH. A file that already carries a `.local/bin` (or `.local\\bin`)",
        "PATH line is left alone.",
        "",
        "A fleet that could not be sampled — its containers not started, or",
        "every unit hosted — is locked",
        "approved on no evidence only once you say so: setup says why and what",
        "that means, and asks `Lock it approved on no evidence? [y/N]`. With",
        "flags, setup binds the servers already answering and starts none, so",
        "nothing is sampled; `--accept-unsampled` is that acknowledgment, and",
        "without it nothing is locked. Backends on another machine come in with",
        "`--host` (repeatable).",
        "",
        "A locked fleet is promoted to a folder of its own under",
        "`$MCGYVR_HOME/fleets/` and named in `$MCGYVR_HOME/live.json`, with",
        "`serving.enable_sleep_wake` on and its launch specs in the staged folder",
        "(`serving.compose_dir`), so a request to a unit that is down wakes it",
        "through the door. That live fleet is the config every command reads,",
        "wherever it is run, unless `$MCGYVR_CONFIG` or `--config DIR` names",
        "another; a `fleet.yaml` in the working directory is not read. Setup",
        "stages in `PATH` or `--config DIR` when one is named, and there refuses",
        "to overwrite a setup without `--force`.",
        "",
        "A hosted API unit comes in with `--api` (repeatable), written as",
        "`model=<id>,address=<url>,api_key_env=<VAR>` — so a machine with no",
        "GPU and no local backend gets the same two files rather than a",
        "refusal. `api_key_env` is the NAME of the environment variable",
        "holding the key; the key itself is never written to either file.",
        "A machine with no local backend and no `--api` still refuses, because",
        "a config that dispatches nowhere is not a head start.",
        "",
        "What the config is for comes in with these, all optional:",
        "",
        "- `--use-case` — `mcgyvr-code` (the default), `code`, `chat` or `agent`;",
        "  see *Use cases and switches* below.",
        "- `--deployment` — `hybrid` (an API-tier session agent drives mcgyvr) or",
        "  `local-only` (mcgyvr is the backend); the default is `local-only` for",
        "  `chat` and `hybrid` otherwise.",
        "- `--priority` — compose the ladder for `throughput`, `quality` or",
        "  `cost` instead of the default ladder.",
        "- `--profile` — deprecated, removed in the release after next: use",
        "  `--priority`. A word naming a priority maps onto it, other text is",
        "  ignored, and either way it warns.",
        "- `--jev UNIT` — dedicate VRAM to a Jev unit, the written unit every",
        "  typed decision asks; it is never slept or woken.",
        "",
        "`mcgyvr setup --help` has each one's full text.",
        "",
        "Two commands measure and plan before `mcgyvr setup` writes a config.",
        "`mcgyvr scan` measures this machine (free and total VRAM, available RAM,",
        "cores, timed memory bandwidth, free disk), records it as this machine's",
        "rig file (`localhost.json` in the rig-file folder, `$MCGYVR_RIGS`, by",
        "default `~/.mcgyvr/rigs`), says what moved since the last record, and",
        "exits 4 when a card, total RAM, the cores or the bandwidth moved.",
        "`mcgyvr recommend --profile code --users N --host RIG` re-reads each",
        "rig over ssh and prints one JSON plan: which checkpoint and engine serve",
        "that profile, from `--model-store DIR` when a checkpoint there fits,",
        "otherwise from the use case's candidates on the Hugging Face Hub",
        "(ranked by downloads; the cache of an earlier read, then the shipped",
        "model catalog, when the Hub cannot be asked), says which answered,",
        "and names the host it goes on. `chat` and `agent` plan one unit: the",
        "biggest model that fits, at the most context that fits and at least",
        "8192 per user. It wakes and sleeps nothing, and writes nothing but that",
        "cache.",
        "",
        "A setup is two files in one directory, and `mcgyvr setup` writes both",
        "(staged under the data folder, as above):",
        "",
        f"- `{FLEET_FILENAME}` — what runs where: `units`, `rigs` and `fleets`.",
        f"- `{POLICY_FILENAME}` — how work moves over those units: `ladder` and "
        "every other top-level key below but `relief`.",
        "",
        f"A third file, `{RELIEF_FILENAME}`, holds `relief`: the units other",
        "people lend you through a hub. `mcgyvr rig rungs sync` writes it whole",
        "and nothing else does, so it is neither locked nor edited by hand.",
        "",
        "Each file refuses a key that belongs in the other. `rigs`, `fleets` and",
        "each unit's `unit_id` are not in the tables below: the fleet lock",
        "keys on them, and the run config drops them when it loads the",
        "setup. A `fleets` entry takes `layout` and `next`; a `rigs` entry is",
        "checked only as a block. `examples/fleet.yaml` shows all three.",
        "",
        "`mcgyvr local_pool` reads that config back: the usable rungs "
        "cheapest-first with",
        "their family, attempt budget and model; the escalation ceiling and where it",
        "came from; every skipped rung with the reason it was skipped; and the",
        "orchestrator and verifier models. `--probe` also asks each unit whether it",
        "is answering — off by default, because resolving a ladder should not need",
        "a network. Run it whenever a run picks a rung you did not expect.",
        "",
        "Three keys across the two files are the levers, and `mcgyvr local_pool` "
        "is how",
        "you read all three:",
        "",
    ]
    for lever in _LEVERS:
        lines.append(f"- `{lever}` — {_escape(by_name[lever].doc)}")
    lines += [
        "",
        "`mcgyvr config` prints the resolved config; `mcgyvr detect` shows what",
        "can run the work; `mcgyvr capabilities` shows the shipped capability table.",
        "",
        *_macos_windows_section(),
        *_use_cases_section(),
        "## Value types",
        "",
        "| Type | Accepted |",
        "| --- | --- |",
    ]
    for name, rule in _TYPES:
        lines.append(f"| {name} | {_escape(rule)} |")
    lines += ["", "## Top-level keys", ""]
    lines += _table(SCHEMA, "")

    for field in SCHEMA:
        if field.block:
            lines += _section(field, field.name, 2, dotted=True)

    return "\n".join(lines).rstrip("\n") + "\n"


#: The width the switch records are wrapped at, inside the house limit of 105.
_SWITCH_WIDTH = 100


def _use_cases_section() -> list[str]:
    """SETUP.md's *Use cases and switches*: the four use cases, then one record
    per point of `SWITCHES` -- its keys, what off means and what it does -- then
    the four knobs by their plain names."""
    lines = [
        "## Use cases and switches",
        "",
        "`use_case` in the policy says what this install serves, and",
        "`mcgyvr use NAME` switches it (`/mcgyvr-use` is the same for a session):",
        "",
        "- `mcgyvr-code` — mcgyvr between the model and you: contracts proposed,",
        "  vetted, run up the ladder, gated, repaired, reviewed and re-planned,",
        "  each point under its own switch below, every one on by default. A",
        "  policy that names no use case is `mcgyvr-code`. A batch runs",
        "  `--jobs auto` (the fleet's slots), and proposals are authored by the",
        "  classifier when a Jev unit is bound and on.",
        "- `code` — a coding model mcgyvr recommends, served raw.",
        "- `chat` — a text model served raw.",
        "- `agent` — a model with tool-calling served raw.",
        "",
        "Under `code`, `chat` and `agent` nothing below runs: `mcgyvr PROMPT` and",
        "`mcgyvr direct` refuse (exit 3) and name `mcgyvr use mcgyvr-code`.",
        "`coding`, the old name, is refused naming the two that replaced it.",
        "",
        "Every switch but `--jobs` lives in the policy file. Off is the value",
        "that takes mcgyvr out of that point:",
        "",
    ]
    for s in SWITCHES:
        keys = ", ".join(f"`{key}`" for key in s.keys)
        lines += textwrap.wrap(
            f"- **{s.point}** ({keys}; off {s.off}): {s.doc}.",
            width=_SWITCH_WIDTH,
            subsequent_indent="  ",
            break_on_hyphens=False,
        )
    lines += [
        "",
        "The four knobs, by their plain names:",
        "",
    ]
    for number, name in KNOBS.items():
        (knob,) = (s for s in SWITCHES if s.knob == number)
        keys = ", ".join(f"`{key}`" for key in knob.keys)
        lines.append(f"{number}. {name} — {keys}.")
    lines += [
        "",
        "A single model is a `ladder` of one unit, or `max_escalations: 0`, which",
        "keeps a climb on the rung it starts on. Vetting has no switch: it is what",
        "makes a proposal a runnable contract. Model loading, slots, the sandbox,",
        "locks and waking a card are machinery, not switches.",
        "",
    ]
    return lines


#: Where the /mcgyvr-use skill is written, beside the /mcgyvr one.
USE_SKILL_PATH = Path("skills/mcgyvr-use/SKILL.md")


def render_use_skill() -> str:
    """Render the /mcgyvr-use skill: switch the use case from a session."""
    names = ", ".join(f"`{name}`" for name in USE_CASES)
    lines = [
        "---",
        "name: mcgyvr-use",
        'description: "Switch mcgyvr between mcgyvr-code (every stage on) and a raw '
        'model: code, chat or agent."',
        "disable-model-invocation: true",
        "---",
        "",
        SKILL_MARKER,
        "",
        "# /mcgyvr-use",
        "",
        f"Switch the use case of the setup mcgyvr reads. NAME is one of {names}.",
        "",
        "```",
        "mcgyvr use NAME [--config PATH]",
        "```",
        "",
        "It rewrites the `use_case:` line of the setup's `policy.yaml` and",
        "nothing else, then prints the use case before and after and the stages",
        "that are now on or off. Show the user what it printed.",
        "",
        "- `mcgyvr-code` opts in: contracts are proposed, vetted, run up the",
        "  ladder, gated, repaired, reviewed and re-planned, each under its own",
        "  switch in the policy, every one on by default.",
        "- `code`, `chat` and `agent` serve the model raw: no stage runs, and",
        "  `mcgyvr PROMPT` and `mcgyvr direct` refuse until `mcgyvr use",
        "  mcgyvr-code`.",
        "",
        "Each switch, and what off means, is listed under *Use cases and",
        "switches* in `skills/mcgyvr/SETUP.md`. `coding` is not a use case: the",
        "command refuses it and names `mcgyvr-code` and `code`.",
    ]
    return "\n".join(lines) + "\n"


# The example contracts examples.md prints, keyed by name: one `code` contract a
# model has to satisfy, and one per deterministic operation, each named after the
# operation so `render_examples` can sort it by whether `catalog()` lists that
# name. A value is a whole YAML document held as a string, ready to drop into a
# fenced block verbatim; the test suite loads every one through the contract
# validator, so an example you copy is an example known to load.
_EXAMPLE_TEMPLATES: dict[str, str] = {
    "format": """\
id: format-pkg
task_type: code
operation: format
task: Reformat the module with the project's formatter.
target: src/pkg/messy.py
scope:
  allow: ["src/pkg/**"]
""",
    "import_sort": """\
id: sort-imports
task_type: code
operation: import_sort
task: Order the module's imports with the project's import sorter.
target: src/pkg/messy.py
scope:
  allow: ["src/pkg/**"]
""",
    "lint_fix": """\
id: lint-pkg
task_type: code
operation: lint_fix
task: Apply the linter's own autofixes to the module.
target: src/pkg/messy.py
scope:
  allow: ["src/pkg/**"]
""",
    "rename_symbol": """\
id: rename-fetch
task_type: code
operation: rename_symbol
task: Rename fetch_page to fetch_document in the module.
target: src/pkg/messy.py
rename:
  from: fetch_page
  to: fetch_document
scope:
  allow: ["src/pkg/**"]
""",
    "code": """\
id: impl-chunk
task_type: code
task: >-
  Implement chunk. Split a list into consecutive groups of at most size
  elements, preserving order; the last group is shorter when the length does
  not divide evenly. An empty list yields an empty list. Raise ValueError
  unless size is a positive integer.
target: src/pkg/chunk.py
interface: "def chunk(items: list[T], size: int) -> list[list[T]]"
stop_conditions:
  - Whether a size larger than the list is an error or one group is not stated.
demonstration: ["pytest -q tests/test_chunk.py"]
scope:
  allow: ["src/pkg/chunk.py"]
""",
}


def examples() -> dict[str, str]:
    """Return the example contracts as a copy, so callers cannot mutate them."""
    return dict(_EXAMPLE_TEMPLATES)


#: The example contracts, materialised once at import time by `examples()`.
EXAMPLES: dict[str, str] = examples()


def _contract_default_label(field: contract_schema.Field) -> str:
    if field.required:
        return "—"
    if field.kind in ("block", "block_list"):
        return "—"
    if field.kind in ("str_list", "glob_list"):
        return "`[]`" if not field.default else f"`{list(field.default)}`"
    if field.default is None:
        return "unset"
    if field.default == "":
        return "empty"
    if field.kind == "bool":
        return f"`{str(field.default).lower()}`"
    return f"`{field.default}`"


def _contract_describe(field: contract_schema.Field) -> str:
    text = field.doc
    if field.hint:
        text = f"{text} {field.hint.rstrip('.')}."
    return f"{text} (worker-facing)" if field.worker_facing else text


def _wrap(text: str, first: str = "", rest: str = "  ") -> list[str]:
    """`text` as Markdown lines of at most `WIDTH` characters.

    `first` opens the first line and `rest` every other one, so a list item's
    continuation lines stay inside the item. A word is never broken.
    """
    return textwrap.wrap(
        text,
        width=WIDTH,
        initial_indent=first,
        subsequent_indent=rest,
        break_long_words=False,
        break_on_hyphens=False,
    )


def _contract_records(
    fields: Sequence[contract_schema.Field], prefix: str
) -> list[str]:
    """One record per contract key: a bold key line, then its type and its doc.

    A record list rather than a table, so no line runs past `WIDTH`.
    """
    lines: list[str] = []
    for field in fields:
        default = _contract_default_label(field)
        if field.required:
            kind = f"{_type_label(field)}; required"
        elif default == "—":
            kind = f"{_type_label(field)}; optional"
        else:
            kind = f"{_type_label(field)}; optional, default {default}"
        lines += [f"**`{prefix}{field.name}`**", *_wrap(f"- type: {kind}")]
        lines += [*_wrap(f"- description: {_contract_describe(field)}"), ""]
    return lines


def _contract_section(field: contract_schema.Field, path: str) -> list[str]:
    lines = [f"#### `{path}`", "", *_wrap(field.doc, rest=""), ""]
    if field.kind == "block_list":
        lines += ["An ordered list. Each entry takes these keys:", ""]
    lines += _contract_records(field.block, f"{path}.")
    for inner in field.block:
        if inner.block:
            lines += _contract_section(inner, f"{path}.{inner.name}")
    return lines


def _flags(names: Sequence[str]) -> list[str]:
    """A list item per flag in `names`, its help the words the CLI's own is built
    from (`mcgyvr.flagset`), so the skill and the CLI cannot say two things."""
    from mcgyvr.flagset import HELP

    lines: list[str] = []
    for name in names:
        metavar, help_text = HELP[name]
        if name == "--commit":
            shown = "`--commit`, `--no-commit`"
        else:
            shown = f"`{name} {metavar}`" if metavar else f"`{name}`"
        lines += _wrap(f"- {shown} — {help_text.replace('%%', '%').rstrip('.')}.")
    return lines


def _ended() -> list[str]:
    """How a batch ended, by its exit code; both verbs exit the same way.

    The `--log` record and its kinds are for a script that called mcgyvr, not
    for a session agent, so the skills say the codes in words (#792).
    """
    return [
        "- 0 — the contracts were planned (and, unless `--output`, every one that ran",
        "  ended well).",
        "- 1 — a failure: the config, the proposer or its reply, the repository, a",
        "  run that did not land its change, or a crash; stderr says which.",
        "- 2 — usage: a flag that cannot be honoured or has no meaning on this side, a",
        "  contract path that is not there, or no session to file the runs under.",
        "- 3 — refused: no proposer is configured, no contract came of the prompt or",
        "  passed vetting, or a contract was held and never sent (`blocked`).",
        "",
        "`--help` prints the same table.",
        "",
    ]


#: Said by both skills, once: what a sandbox is built from, and who a run is
#: filed under.
_HEAD_AND_SESSION: tuple[str, ...] = (
    "Every run works on the repository as committed at HEAD: uncommitted edits",
    "and untracked files, including a test you just wrote, are not in the",
    "sandbox. A batch refuses unless it can say who typed it: Claude Code and Pi",
    "sessions are detected from the environment, otherwise pass `--session ID`.",
)

#: The flags the /mcgyvr skill names: the ones a prompt's batch is steered by.
_PROMPT_FLAGS: tuple[str, ...] = (
    "--jobs",
    "--commit",
    "--branch",
    "--session",
    "--record",
    "--output",
)

#: The flags the /mcgyvr-direct skill names: the prompt's, and the two that
#: only a set someone wrote can use.
_DIRECT_FLAGS: tuple[str, ...] = (*_PROMPT_FLAGS, "--result", "--notes-from")


def render_skill() -> str:
    """Render the /mcgyvr skill: a prompt, planned into contracts and run.

    Thin on purpose: it says how to hand the user's words to `mcgyvr "<prompt>"`,
    what happens to them, how to read how the batch ended and where its results
    are, and that work it refused or could not finish goes to /mcgyvr-direct.
    How a contract is written is /mcgyvr-direct's (`render_direct_skill`). The
    flags' help is the words the CLI's own is built from (`mcgyvr.flagset`), so
    this file cannot describe a flag differently from the CLI.
    """
    lines = [
        "---",
        "name: mcgyvr",
        'description: "Offload a coding request to mcgyvr, a CLI that plans a prompt '
        "into task contracts and runs them on deterministic tools, local models or "
        "API models, keeping only what its deterministic gate accepts. Pass the "
        "user's words as the prompt: mcgyvr surveys the repository, a proposer "
        "proposes contracts, every proposal is vetted, and the contracts that pass "
        "run in dependency order. It never loads itself; invoke it with /mcgyvr "
        "<prompt>. Contracts you write yourself, or ones it refused or could not "
        'finish, go to /mcgyvr-direct."',
        "disable-model-invocation: true",
        "---",
        "",
        PROMPT_SKILL_MARKER,
        "",
        "# /mcgyvr",
        "",
        "Offload a coding request to mcgyvr in the user's own words. mcgyvr plans it",
        "into contracts (one target, one task, one way to judge it each), runs them,",
        "gates every answer deterministically, and leaves accepted `code` changes in",
        "the working tree. It never commits unless told to, and it never writes",
        "anything else into the repository.",
        "",
        "## Run it",
        "",
        "```",
        'mcgyvr "<prompt>" [--repo PATH] [flags]',
        "```",
        "",
        "The prompt is everything the user wrote after `/mcgyvr`, passed as one",
        "argument; one whose first word is a command name goes after `--`",
        '(`mcgyvr -- "<prompt>"`). The contracts planned are printed on stdout, and',
        "what happens to them on stderr.",
        "",
        *_HEAD_AND_SESSION,
        "",
        "## What it does",
        "",
        "```",
        "prompt -survey-> evidence -propose-> proposals -vet-> contracts | refusals",
        "       -schedule-> tree -run-> settle -(spent)-> replan",
        "```",
        "",
        "Planning is survey, propose and vet. mcgyvr reads the repository for the",
        "evidence the prompt points at, and the proposer bound in the config proposes",
        "contracts from it. Every proposal is vetted: its target is a file the index",
        "holds, each dependency's signature is in the index or in a contract that",
        "creates it, what the worker is shown fits its ceiling, and its id is unused.",
        "One that fails is a refusal, printed as `refused:` with a `change:` line",
        "saying what to change.",
        "",
        "Dispatch is schedule, run, settle and replan. The contracts that passed go on",
        "one dependency tree and run in the order it allows, each settled as it ends.",
        "One whose provider did not land is held, never sent (`blocked`). One whose",
        "ladder is spent goes back to the proposer with its failure notes, and what",
        "comes back runs in its place, up to `max_replans` times.",
        "",
        "## Flags that matter",
        "",
        *_flags(_PROMPT_FLAGS),
        "",
        "`mcgyvr direct -h` lists every flag; both verbs take the same set.",
        "",
        "## How it ended",
        "",
        *_ended(),
        "## Where the results are",
        "",
        "Nothing on stdout points at a result. Each contract that ran has a result",
        "file under the config's `journal.dir`, as `results/<id>-<stamp>.json`;",
        "`--record DIR` puts a complete copy of each under `DIR/results/`. Read",
        "`outcome` first: the /mcgyvr-direct skill lists every key of the file. An",
        "`accepted` change is in its target, uncommitted unless `--commit` or",
        "`--branch NAME` was given: review it there and commit it yourself.",
        "",
        "## Refused or spent: hand it to /mcgyvr-direct",
        "",
        "A refusal, a contract held `blocked` behind one, and a contract whose ladder",
        "is spent past `max_replans` are work this batch will not finish. Finish it",
        "with /mcgyvr-direct: write the contracts yourself, or plan again with",
        "`--output DIR`, which writes each contract that passed vetting to",
        "`DIR/<id>.json` and runs none, fix those files from the refusals and the",
        "findings, and run them with `/mcgyvr-direct DIR`.",
    ]
    return "\n".join(lines).rstrip("\n") + "\n"


#: What the result file's `outcome` says, and what it leaves to do next.
_OUTCOMES: tuple[str, ...] = (
    "- `outcome` — one word, and what it leaves to do next:",
    "  - `accepted` — the work landed; nothing to replan.",
    "  - `rejected` — the deterministic gate refused the change; the",
    "    findings name the check a different contract has to answer.",
    "  - `delivery_refused` — judged acceptable, but the write to the tree",
    "    was refused; `detail` says what was in the way. Clear it, rerun.",
    "  - `nothing_to_change` — a tool found nothing to do; exit 0.",
    "  - `ladder_spent` — everything this machine offers was tried and none",
    "    produced an acceptable change. Raising a number changes what it",
    "    costs to fail, not whether it fails. In a batch planned from a",
    '    prompt (`mcgyvr "<prompt>"`) the contract goes back to the proposer',
    "    with its failure notes and what comes back runs in its place, up to",
    "    `max_replans` (default 1); `replanned` says what became of it. Under",
    "    `mcgyvr direct` no proposer is asked and nothing re-plans it: you",
    "    do, from the findings (Step 5).",
    "  - `escalation_ceiling` — stopped at a ceiling on how far the work may",
    "    be moved up, with dearer tries never entered; that says it was not",
    "    allowed to try, not that it cannot. Rerun where those moves are",
    "    paid for.",
    "  - `attempt_ceiling` — stopped at what one task may spend, which",
    "    bounds the bill and not the ability. Rerun against a budget that",
    "    can pay for it.",
    "  - `nothing_to_run` — nothing on this machine offered to do this work",
    "    at all, so the machine stopped it and not the work. A different",
    "    contract cannot fix it: `skills/mcgyvr/SETUP.md` can.",
    "  - `declined_throughout` — everything offered stepped aside without",
    "    spending an attempt, so nothing claims a contract of this shape.",
    "    A different contract cannot fix this either; that same file can.",
    "  - `blocked` — held by the dependency tree (`dependents: hold`): a",
    "    contract it waits on did not land, or landed without a symbol it",
    "    needs, so it was never sent and no attempt was spent; exit 3.",
    "    `blocked_by` says who and what. Rerun once that one lands.",
    "  - `error` — an exception before any verdict was reached: the failure",
    "    is in the machinery, not the work. `detail` names the cause.",
)

#: Every other key of the result file.
_RESULT_KEYS: tuple[str, ...] = (
    "- `attempts[]` — every try: `rung`, `attempt`, `verdict` (`passed`,",
    "  `failed`, `declined`, `error`), `detail`, `findings` (the gate's lines",
    "  behind a failure), `notes` (the record those lines are rendered from;",
    "  below), `attempt_id`, `draw`, `draws`, `rows`, `relief`,",
    "  `model`, `address`. `draws` is the",
    "  breadth the attempt asked for (`breadth.draws`), whatever the verdict;",
    "  `rows` is how many of those draws left a journal row, which is `draws`",
    "  unless the attempt raised part-way and `0` for a try that declined or",
    "  raised before dispatching. `draw` is the draw the entry is about, and is",
    "  `null` — with `attempt_id` `null` beside it — on an `error` no single",
    "  dispatch caused: `rows: 0` means it raised before dispatching at all,",
    "  and anything more means it raised past draw `rows - 1`. `relief` is",
    "  `true` for a rung lent through a hub — recorded like any try, but",
    "  charged against the budget only when it passes — and `model`/`address`",
    "  name the unit that served it, so a relief try shows which borrowed",
    "  machine answered.",
    "- `assurance` — what an `accepted` result rests on, and `detail` says it",
    "  in a sentence: `deterministic` (a tool's change, on the gate),",
    "  `verified` (a reviewer agreed), `unverified` (no reviewer could be",
    "  asked; `detail` says why) or `unchecked` (a reply no check judges:",
    "  no checks, no review). A reply is never reviewed.",
    "- `findings` — why a change was refused, one line per reason: the",
    "  deterministic gate's findings for a contract that dispatched nothing,",
    "  or what refused the write on a `delivery_refused`.",
    "- `delivery` — where the work went: left uncommitted in the tree (the",
    "  default), the commit, or why it was refused (as `detail`).",
    "  `committed`, `commit`, `branch`, `handoff` are the commit as fields.",
    "- `target`, `contract`, `task_type`, `session` (the session the run is",
    "  filed under; also written as `orchestrator`, its old key, for one",
    "  release), `run`, `session_file`, `journal`, `exit_code`.",
    "- `copy_errors` — a `--record DIR` copy that could not be written, and",
    "  why. Empty on almost every run. mcgyvr's own record under `journal`",
    "  is complete whatever this says; a copy is not a sink and its failure",
    "  does not stop a run.",
    "- `notes` — what the run said in passing (not failure notes): the",
    "  uncommitted and untracked paths the sandbox of HEAD left out, what a",
    "  tool printed as it worked (what a rename renamed), what the baseline",
    "  left behind (now cleaned up), and a relief rung that duplicates a unit",
    "  this install serves.",
    "- `triage` — only under `triage: jev` or a contract's `start_rung`: the",
    "  `rung` the climb started on and its `source` (`jev`, asked for this",
    "  run, or `contract`); for `jev`, every rung's `probabilities`, its",
    "  `confidence` and the `model` asked, or a `fallback` saying why the",
    "  climb started on its first rung.",
    "- `blocked_by` — only on a `blocked` result: the `reason`",
    "  (`provider_failed`, `provider_not_landed`, `provider_landed_without`,",
    "  `provider_blocked`, `cycle`, `unknown_dependency`, `unprovided`), the",
    "  `providers` it waited on with the `outcome` and `result` each came",
    "  to, the `needs` it had of them (`path`, `symbol`, and `creates`: to",
    "  be created rather than changed) and the `chain` a hold came down",
    "  through. A repository's live tree, which every batch on it joins",
    "  while it has contracts in flight, is under `journal.dir` in",
    "  `trees/<tree>.json`.",
    "- `seeded` — only on a run started with `--notes-from RESULT`: `from`,",
    "  the result read, `records`, the failure-notes records read from it,",
    "  each with the `run` it was made in, and `handed`, how many the climb",
    "  opened with (all under `retry_notes: climb`, else none).",
    "- `replanned` — only on a `ladder_spent` result in a batch planned from a",
    "  prompt with `max_replans` above 0: the `round`, the `max_replans` it was",
    "  held to, the ids of the `contracts` proposed in its place (empty when it",
    "  was not re-planned; each of those contract files carries `replan`: the",
    "  id it `replaces` and its `round`) and a `detail` sentence, which",
    "  `detail` repeats.",
)


def render_direct_skill() -> str:
    """Render the /mcgyvr-direct skill: contracts you wrote, vetted and run.

    The front matter and the walkthrough prose are fixed; the contract key
    records and their nested sections are rendered from the contract `SCHEMA`,
    the deterministic operation names from `contract_schema.operations()`, the
    failure-notes records from `mcgyvr.notes`, and the flags' help from
    `mcgyvr.flagset`, the words the CLI's own is built from.
    """
    lines = [
        "---",
        "name: mcgyvr-direct",
        'description: "Run task contracts you wrote with mcgyvr, a CLI that runs each '
        "on deterministic tools, local models or API models and keeps only what its "
        "deterministic gate accepts. Pass contract files or a directory of them: "
        "mcgyvr vets each one as it vets a proposal, prints every refusal with what "
        "to change, and runs the rest in dependency order. Use it when a change has "
        "one target and a way to judge it, or for work /mcgyvr refused or could not "
        "finish: write the contracts, validate them, run them, read the result "
        "files, replan from the findings. It never loads itself; invoke it with "
        "/mcgyvr-direct <files|dir>. The schema below is the only contract "
        'vocabulary."',
        "disable-model-invocation: true",
        "---",
        "",
        SKILL_MARKER,
        "",
        "# /mcgyvr-direct",
        "",
        "Run contracts you wrote. A *contract* is one target, one task and one way to",
        "judge it; mcgyvr vets each one exactly as it vets a proposal from a prompt,",
        "runs the ones that pass in the order their dependency tree allows, gates",
        "every answer deterministically, and leaves an accepted `code` change in the",
        "working tree. It never commits unless told to, and it never writes anything",
        "else into the repository. No proposer is asked: refusals and spent work come",
        "back to you.",
        "",
        "## Step 1 — write the contracts",
        "",
        "One YAML or JSON file per contract. Every key below is the contract schema in",
        "`src/mcgyvr/contract.py`, rendered by `make docs`; unknown keys are refused,",
        "and every rejection names the key and what a valid value looks like. Pick",
        "the `task_type` first. For `code`, evidence is derived from the contract's",
        "own fields, never chosen; `operation:` has a tool make the change instead.",
        "`mcgyvr catalog <type>` prints the type's guarantee. A contract that needs",
        "another's work names its id in `depends_on`.",
        "",
        "### Keys",
        "",
    ]
    lines += _contract_records(contract_schema.SCHEMA, "")
    for field in contract_schema.SCHEMA:
        if field.block:
            lines += _contract_section(field, field.name)
    lines += [
        "### Deterministic operations",
        "",
        *_wrap(
            "Not task types: `task_type: code` with `operation:` "
            + ", ".join(f"`{op.name}`" for op in contract_schema.operations())
            + " has a tool make the change, never a model.",
            rest="",
        ),
        "",
        "### Minimal examples",
        "",
        f"`references/{EXAMPLES_PATH.name}` carries one `code` contract and one per",
        "operation, each loaded through the contract validator by the test suite, so",
        "copying one is copying a shape that is known to validate.",
        "",
        "## Step 2 — validate before spending anything",
        "",
        "```",
        "mcgyvr contract CONTRACT.yaml",
        "```",
        "",
        "Prints what the contract resolves to, or names the key that is wrong. Fix",
        "the contract; never guess a field. A `code` contract states no reply",
        "cap: every request is sent the most its unit can give.",
        "",
        "## Step 3 — vet and run the set",
        "",
        "```",
        "mcgyvr direct FILE... | DIR [--repo PATH] [flags]",
        "```",
        "",
        "A directory is read for its `*.json`, `*.yaml` and `*.yml` files. Each",
        "contract is vetted as a proposal is: its target is a file the index holds,",
        "each dependency's signature is in the index or in a contract of the set that",
        "creates it, what the worker is shown fits its ceiling, and no other contract",
        "states the same work; a file that does not load, two files giving one id,",
        "and a contract waiting on a refused one are refused too. Every refusal is",
        "printed on stderr as",
        "",
        "```",
        "  refused: <file>: <reason>",
        "    change: <what_to_change>",
        "```",
        "",
        "The rest of the set runs. Change each refused file as its directive says",
        "and run those files again, with what waits on them; not the whole set,",
        "whose accepted changes are already in the tree. When no contract passes,",
        "nothing runs and the exit is 3. `--output DIR` vets only: what passed is",
        "written to `DIR/<id>.json` and nothing runs.",
        "",
        *_HEAD_AND_SESSION,
        "",
        "### Flags that matter",
        "",
        *_flags(_DIRECT_FLAGS),
        "",
        "`mcgyvr direct -h` lists every flag. `--budget` is refused here: there is",
        "no prompt to read.",
        "",
        "### How it ended",
        "",
        *_ended(),
        "## Step 4 — read the result files",
        "",
        "Nothing on stdout points at a result. For a set of one contract, name where",
        "you read it with `--result PATH`; for more, pass `--record DIR` and read",
        "`DIR/results/<id>-<stamp>.json`. Either way mcgyvr keeps its own copy under",
        "the config's `journal.dir`, in `results/`. The file's keys:",
        "",
        *_OUTCOMES,
        *_RESULT_KEYS,
        "",
        *_notes_section(),
        "Every run is journaled under the config's `journal.dir` and nothing on",
        "the command line moves it — that one directory is where every run can",
        "be counted. Deterministic runs are there too, as a row naming",
        "the program that did the work with `tier: deterministic` and no prompt",
        "or reply beside it. `--record DIR` adds a complete second copy for your",
        "own use. `--notes-from RESULT` starts a contract's climb with an earlier",
        "run's failure notes, under a banner naming that run: for a rerun on another",
        "ladder or machine, never instead of replanning.",
        "",
        "## Step 5 — replan from the findings, never retry the same contract",
        "",
        "A failed attempt already had its retries inside the run, and under",
        "`mcgyvr direct` a spent ladder is not handed to a proposer: the next",
        "contract is yours to write. When `outcome` is not `accepted`, read",
        "`attempts[].findings`: each line is one reason the gate refused.",
        "`attempts[].notes` is the same evidence as a record, one per failed",
        "attempt in climb order: the check, the file and line, the tool's code, and",
        "the command and its exit where the check ran one. Write a *different*",
        "contract — narrower target, an acceptance command that states the",
        "requirement, a stop condition for what was ambiguous — and go back to",
        "Step 2. Running the same contract again spends more on the same answer.",
        "",
        "`nothing_to_run` and `declined_throughout` are the exception: neither is",
        "fixable by writing a different contract, because both say this machine",
        "offered nothing that would do the work. Rewriting only relocates the same",
        "answer. Report it to whoever owns the machine; the remedy is in",
        "`skills/mcgyvr/SETUP.md`.",
        "",
        "When `outcome` is `accepted`, the change is in `target` (a rename's: in",
        "each file `delivery` names), uncommitted. Review it there and commit it",
        "yourself. To have mcgyvr commit instead, run with `--commit` or",
        "`--branch NAME` on a tree where those files are clean: mcgyvr refuses to",
        "overwrite an edited or uncommitted file, so restore it first",
        "(`git checkout -- <target>`) rather than rerunning on top of the last run.",
    ]
    return "\n".join(lines).rstrip("\n") + "\n"


def _notes_records(fields: Sequence[Field]) -> list[str]:
    """A failure-notes field record: key, type (`or null` when optional), meaning."""
    lines: list[str] = []
    for field in fields:
        kind = (
            f"`{field.choices[0]}`"
            if field.kind == "enum" and len(field.choices) == 1
            else _type_label(field)
        )
        if not field.required:
            kind += " or null"
        lines += [f"**`{field.name}`**", *_wrap(f"- type: {kind}")]
        lines += [*_wrap(f"- description: {field.doc}"), ""]
    return lines


def _notes_section() -> list[str]:
    """The skill's account of `attempts[].notes`, its records from `mcgyvr.notes`."""
    return [
        "`attempts[].notes` is the failure-notes record of a failed try, `null` on",
        "a try that left none. It is built from what the gate, the reviewer or the",
        "reply parser observed — never from a model's account — so an optional",
        "field is `null` where the check reported nothing for it. Its JSON Schema",
        f"is `references/{NOTES_SCHEMA_PATH.name}`. The record:",
        "",
        *_notes_records(failure_notes.NOTES_FIELDS),
        "Each entry of its `notes`:",
        "",
        *_notes_records(failure_notes.NOTE_FIELDS),
    ]


def render_notes_schema() -> str:
    """The failure-notes JSON Schema, as the file `make docs` writes."""
    return json.dumps(failure_notes.json_schema(), indent=2, ensure_ascii=False) + "\n"


def render_examples() -> str:
    """Render examples.md: every example contract, split into two sections.

    A name `catalog()` lists as a deterministic operation goes under the
    operations heading and every other name under the one a model satisfies;
    within a section the order is the order of `_EXAMPLE_TEMPLATES`.
    """
    operation_names = {op.name for op in catalog().operations}
    type_examples = {
        name: text for name, text in examples().items() if name not in operation_names
    }
    operation_examples = {
        name: text for name, text in examples().items() if name in operation_names
    }
    lines = [
        SKILL_MARKER,
        "",
        "# One minimal `code` contract, and one per deterministic operation",
        "",
        "Each loads through the contract validator; they are checked by the test",
        "suite, so copying one is copying a shape that is known to validate. The",
        "keys are documented in the /mcgyvr-direct skill, `SKILL.md`.",
        "",
        "## A change a model makes",
        "",
    ]
    for name, text in type_examples.items():
        lines += [f"### `{name}`", "", "```yaml", text.rstrip("\n"), "```", ""]
    lines += [
        "## Deterministic operations (`task_type: code` with `operation:`)",
        "",
    ]
    for name, text in operation_examples.items():
        lines += [f"### `{name}`", "", "```yaml", text.rstrip("\n"), "```", ""]
    return "\n".join(lines).rstrip("\n") + "\n"


def _keys(fields: Sequence[Field], prefix: str = "") -> list[str]:
    """Return every key path in a schema, depth first, parents before children.

    A nested field's path is its ancestors' names joined by dots, which is the
    form the reference's headings and table keys use.
    """
    out: list[str] = []
    for field in fields:
        path = f"{prefix}.{field.name}" if prefix else field.name
        out.append(path)
        out.extend(_keys(field.block, path))
    return out


#: Reading a rendered document back, so its own text can be checked against the
#: schema it came from. `_HEADING` matches the heading `_section` emits: a level
#: of `#`s, a space, and a backticked key path. A heading of any other shape names
#: no section here; it only bounds one, which is how `_sections` finds where a
#: body ends.
_HEADING = re.compile(r"^#+ +`([A-Za-z0-9_.]+)`\s*$", re.MULTILINE)

#: The heading the top-level key table sits under, matched as text rather than by
#: the key-path pattern because it names no key.
_TOP_LEVEL = "## Top-level keys"


def _sections(text: str) -> dict[str, str]:
    """Map each section name in a rendered document to the body beneath it.

    A name is a backticked key path taken from a heading, or `_TOP_LEVEL` for the
    top-level table's heading. A body runs to the next heading of any kind, so a
    section carries its own tables and not its children's.
    """
    starts: list[tuple[int, int, str]] = []
    for match in _HEADING.finditer(text):
        starts.append((match.start(), match.end(), match.group(1)))
    for match in re.finditer(rf"^{re.escape(_TOP_LEVEL)}\s*$", text, re.MULTILINE):
        starts.append((match.start(), match.end(), _TOP_LEVEL))
    # The offset of every heading, whatever its shape: the first one after a
    # section start is where that section's body ends.
    bounds = sorted(
        {match.start() for match in re.finditer(r"^#+ .*$", text, re.MULTILINE)}
    )
    out: dict[str, str] = {}
    for start, body_start, name in sorted(starts):
        after = [b for b in bounds if b > start]
        out[name] = text[body_start : after[0]] if after else text[body_start:]
    return out


def reference_problems(text: str) -> list[str]:
    """Return what a rendered reference fails to document, in plain words.

    The DO NOT EDIT marker has to be the first line, and every key path in
    `SCHEMA` has to be named under its parent's section. An empty list means the
    document agrees with the schema.
    """
    problems: list[str] = []
    if not text.startswith(MARKER):
        problems.append("the DO NOT EDIT marker is not the first line")
    sections = _sections(text)
    absent: set[str] = set()
    for path in _keys(SCHEMA):
        parent, _, leaf = path.rpartition(".")
        where = parent or _TOP_LEVEL
        body = sections.get(where)
        if body is None and parent:
            # The block itself is undocumented, so every key in it is missing for
            # one reason. Report the block once — `absent` keeps the rest of its
            # keys from repeating the finding — and say it is missing entirely,
            # which is a different repair from a section that forgot to name a
            # key it does document.
            if parent not in absent:
                absent.add(parent)
                problems.append(f"the `{parent}` block is not documented at all")
            continue
        if body is None:
            body = ""
        if f"`{leaf}`" not in body:
            problems.append(f"`{path}` is validated and not named")
    return problems


def check_reference(target: Path) -> list[str]:
    """Render the reference into `target`, read it back, delete it, check it.

    The text is validated as the file on disk, and `target` is removed whether
    the check passed, failed or raised.
    """
    rendered = render_reference()
    try:
        target.write_text(rendered, encoding="utf-8")
        text = target.read_text(encoding="utf-8")
    finally:
        target.unlink(missing_ok=True)
    return reference_problems(text)


def _write_or_check(target: Path, rendered: str, schema: str, check: bool) -> int:
    """Write a rendered document, or in check mode compare it with the copy.

    Without `check` it creates the parent directory, writes the document and
    returns 0. With `check` it returns 0 when the file already holds what the
    schema renders, and 1 when the file is stale or missing, after naming the
    document and the schema it was generated from.
    """
    if not check:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered, encoding="utf-8")
        print(f"wrote {target}")
        return 0
    current = target.read_text(encoding="utf-8") if target.exists() else ""
    if current == rendered:
        return 0
    print(
        f"{target}: out of date with SCHEMA in {schema}.\n"
        f"The document is generated from it — a schema change needs it "
        f"regenerated in the same commit.\n"
        f"Run: make docs",
        file=sys.stderr,
    )
    return 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m mcgyvr.docgen",
        description=(
            "Render the configuration reference from the config schema, check it "
            "and delete it; write the /mcgyvr and /mcgyvr-direct skills, the "
            "examples, the failure-notes schema and SETUP.md, or check the "
            "committed ones."
        ),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero if a committed document is not what the schemas render",
    )
    parser.add_argument(
        "--output",
        default=None,
        help=(
            "where the reference is rendered for its check; deleted afterwards "
            "(default: a file under the temporary directory)"
        ),
    )
    parser.add_argument(
        "--skill-output",
        default=str(REPO_ROOT / SKILL_PATH),
        help="where to write the /mcgyvr skill (default: the checkout's copy)",
    )
    parser.add_argument(
        "--direct-skill-output",
        default=str(REPO_ROOT / DIRECT_SKILL_PATH),
        help="where to write the /mcgyvr-direct skill (default: the checkout's copy)",
    )
    parser.add_argument(
        "--setup-output",
        default=str(REPO_ROOT / SETUP_PATH),
        help="where to write SETUP.md (default: the checkout's copy)",
    )
    parser.add_argument(
        "--examples-output",
        default=str(REPO_ROOT / EXAMPLES_PATH),
        help="where to write the examples file (default: the checkout's copy)",
    )
    parser.add_argument(
        "--use-skill-output",
        default=str(REPO_ROOT / USE_SKILL_PATH),
        help="where to write the /mcgyvr-use skill (default: the checkout's copy)",
    )
    parser.add_argument(
        "--notes-schema-output",
        default=str(REPO_ROOT / NOTES_SCHEMA_PATH),
        help=(
            "where to write the failure-notes JSON Schema "
            "(default: the checkout's copy)"
        ),
    )
    args = parser.parse_args(argv)

    reference = (
        Path(args.output)
        if args.output is not None
        else Path(tempfile.gettempdir()) / f"mcgyvr-config-reference-{os.getpid()}.md"
    )
    problems = check_reference(reference)
    if problems:
        print(
            f"{reference}: the reference rendered from SCHEMA in "
            "src/mcgyvr/config.py fails its check, and was deleted:",
            *(f"  {problem}" for problem in problems),
            sep="\n",
            file=sys.stderr,
        )
    else:
        print(f"config reference: rendered to {reference}, checked, deleted")

    stale = _write_or_check(
        Path(args.skill_output),
        render_skill(),
        "src/mcgyvr/flagset.py",
        args.check,
    )
    stale += _write_or_check(
        Path(args.direct_skill_output),
        render_direct_skill(),
        "src/mcgyvr/contract.py",
        args.check,
    )
    stale += _write_or_check(
        Path(args.setup_output), render_setup(), "src/mcgyvr/config.py", args.check
    )
    stale += _write_or_check(
        Path(args.examples_output),
        render_examples(),
        "src/mcgyvr/contract.py",
        args.check,
    )
    stale += _write_or_check(
        Path(args.use_skill_output),
        render_use_skill(),
        "src/mcgyvr/config.py",
        args.check,
    )
    stale += _write_or_check(
        Path(args.notes_schema_output),
        render_notes_schema(),
        "src/mcgyvr/notes.py",
        args.check,
    )
    return 1 if problems or stale else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
