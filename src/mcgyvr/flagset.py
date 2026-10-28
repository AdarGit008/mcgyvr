"""The words of the one flag set `mcgyvr PROMPT` and `mcgyvr direct` share.

Each flag's metavar and help, said once: the command line builds its parser
from them (`mcgyvr.cli.commands.delegate.add_flags`) and the generated skills
quote them (`mcgyvr.docgen`, which may not reach the command line), so a flag
the skills name and the flag the CLI takes cannot say two things.
"""

from __future__ import annotations

#: Option -> (metavar, help) for every flag of the set but `--repo` and
#: `--config`, whose help the command line completes with its defaults.
HELP: dict[str, tuple[str | None, str]] = {
    "--into": (
        "DIR",
        ("clone a URL repo into DIR and keep it, instead of a temp dir"),
    ),
    "--budget": (
        "TOKENS",
        (
            "cap the deterministic read of the prompt at TOKENS estimated "
            "tokens before the proposer is asked (default: the decompose "
            "default). No meaning under `direct`, which reads no prompt: "
            "refused there"
        ),
    ),
    "--output": (
        "DIR",
        (
            "stop once the contracts are planned: write each one that passed "
            "vetting to DIR/<id>.json and run none of them, so `mcgyvr direct "
            "DIR` can run them later. Without it a prompt's contracts are "
            "printed on stdout and run from a temporary directory, and `direct` "
            "runs its files where they are"
        ),
    ),
    "--jobs": (
        "N",
        (
            "run up to N ready contracts at once, each settled as it ends and "
            "the next started as soon as it is ready (default: `auto` under use "
            "case mcgyvr-code, else 1, one at a time). N is capped at the "
            "fleet's total slots, the most dispatches its units take at once; "
            "`auto` or 0 is that cap. Two contracts whose scopes can write one "
            "file never run at once unless the policy says `same_file: "
            "parallel`, and a run's "
            "output is written whole when it ends. Runs beside each other share "
            "the fleet's slots, so one may wait for a rung, or pass a busy one "
            "by, as two runs typed in two terminals would"
        ),
    ),
    "--sandbox": (
        None,
        ("sandbox mode of each run; default is `sandbox.mode`, then `docker`"),
    ),
    "--commit": (
        None,
        (
            "commit each accepted change, or not (--no-commit), whatever "
            "`delivery.commit` says"
        ),
    ),
    "--branch": (
        "NAME",
        ("commit each accepted change onto branch NAME; implies --commit"),
    ),
    "--record": (
        "DIR",
        ("also journal each run under DIR, as a complete second copy"),
    ),
    "--log": (
        "PATH",
        (
            "write how this command ended to PATH as one JSON record "
            "(mcgyvr.delegate_log/1, schema in mcgyvr.delegate_log), on every "
            "exit once the arguments are read, a crash included: its `kind`, "
            "the exit code, the contracts and refusals, and the facts behind a "
            "failure. For a script that called mcgyvr; stderr is unchanged"
        ),
    ),
    "--session": (
        "ID",
        (
            "the session the runs are filed under, resolved before any work "
            "(default: the session that typed this command, and a refusal, exit "
            "2, when there is none); not needed with --output, which runs "
            "nothing"
        ),
    ),
    "--result": (
        "PATH",
        (
            "where *you* read the result file, when the set is one contract "
            "(`direct` with one file); mcgyvr keeps its own copy under the "
            "journal directory either way. Refused for more than one contract, "
            "and for a prompt, whose contracts are not known before it is "
            "planned"
        ),
    ),
    "--notes-from": (
        "RESULT",
        (
            "start a contract's climb with the failure notes of an earlier run "
            "of it: RESULT is that run's result file, and seeds the contract in "
            "the set whose id it names; give it once per contract. Its records "
            "are checked (same contract, the notes schema, repo-relative paths) "
            "and shown to the first attempt under a banner naming the earlier "
            "run, under `retry_notes: climb`; the result's `seeded` says what "
            "was read and handed. For a rerun on another ladder or machine. "
            "Refused for a prompt, whose contracts are proposed new and whose "
            "re-plans carry their own notes"
        ),
    ),
}
