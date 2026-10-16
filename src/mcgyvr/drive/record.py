"""Where attempt records go, and the id one dispatch's row is keyed by."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Recording:
    """Where attempt records go, and which orchestrator is writing them.

    Records carry an orchestrator id and nothing here keeps global mutable
    state, so two orchestrators can share a stream.
    :func:`~mcgyvr.telemetry.observe` takes ``orchestrator`` as a required
    parameter.

    The id is a value the caller constructs rather than something this module
    derives from the process. A default — a hostname, a pid, a literal
    ``"mcgyvr"`` — would be a single-orchestrator assumption: two orchestrators
    sharing a stream would then write rows that agree about who produced them,
    and the field's whole purpose is telling them apart.

    Recording is optional at this seam because a run that cannot write its
    telemetry should fail loudly rather than silently — ``observe`` raises on
    an unwritable sink on purpose — and a caller that has not chosen a sink
    has not chosen to accept that failure. ``mcgyvr run`` always chooses one
    for a dispatching contract: the config's ``journal.dir``, or ``--record``.

    ``path`` is the line sink. The prompts and replies the run dispatches land
    beside it, content-addressed under ``path.parent / "blobs"``, so two
    orchestrators recording into one directory share one blob store and own
    one file each — the layout ``<journal dir>/<orchestrator>.jsonl`` relies
    on.

    ``run`` tells one run of a contract from the next. The orchestrator is
    a whole session, and a session re-runs a contract exactly when the last
    run failed, so without it two runs would key their rows identically and
    :func:`~mcgyvr.telemetry.fold` would bind every correction to the latest
    row — erasing the failure from the folded view. It is the stamp the run's
    result file carries, so a row and its result name the same run.
    """

    path: Path
    orchestrator: str
    run: str = ""
    #: The transcript of the session that typed the command, when the
    #: orchestrator is one (:mod:`mcgyvr.session`). Written on every row so an
    #: attempt can be followed back to the conversation that produced it.
    session_file: Path | None = None
    #: Directories the caller asked for a copy of this journal in (``--record``).
    #: Every line and every blob goes to each of them as well as to
    #: :attr:`path`, which is mcgyvr's own and is the one that cannot move: the
    #: journal is a corpus to be compounded, and a run recorded only in a
    #: directory somebody chose for that run is a run no later question reaches.
    #: A copy lives in a repository as often as not, and repositories are
    #: cloned, go stale and are thrown away.
    mirrors: tuple[Path, ...] = ()
    #: The first failure seen per copy, kept rather than raised. Mutable inside
    #: a frozen record on purpose: the failures are learned while the run is
    #: happening and are reported once when it ends, and the alternative — a
    #: line per row — is thousands of lines about one full disk.
    #:
    #: Out of ``__eq__`` and ``__hash__`` (``compare=False``), which a frozen
    #: dataclass generates from its fields: two recordings pointed at the same
    #: sink are the same recording whatever has since gone wrong with somebody's
    #: copy, and a dict field left in would make this class unhashable the day
    #: anything put one in a set.
    copy_errors: dict[Path, str] = field(default_factory=dict, compare=False)

    def copy_failed(self, mirror: Path, exc: BaseException) -> None:
        """Keep the first thing that went wrong with one copy, and carry on.

        Handed to :mod:`mcgyvr.telemetry` as its ``on_copy_error``. First and
        not last, because the first is the one that says what happened: a
        directory that is a file fails identically on every row after the
        first, and the last failure of a thousand identical ones is no more
        informative than the first and arrives with the wrong timestamp.
        """
        self.copy_errors.setdefault(mirror, f"{type(exc).__name__}: {exc}")

    def __post_init__(self) -> None:
        if not self.orchestrator.strip():
            raise ValueError(
                "an orchestrator id is required to record: a row that cannot "
                "say which orchestrator produced it is the hole the field "
                "exists to close."
            )

    def attempt_id(self, contract: str, rung: str, attempt: int, draw: int = 0) -> str:
        """The id one dispatch's row is keyed by.

        The orchestrator is part of it, and that is not decoration.
        :func:`~mcgyvr.telemetry.fold` binds a correction to the latest row
        carrying this string, so two orchestrators working the same contract on
        the same rung would otherwise share an id, and a correction meant for
        one row would land on the other. The rest is derived rather than random
        so a row can be found again from a report naming the contract, the rung
        and the attempt.

        ``draw`` is here for the same reason the orchestrator is. An attempt
        that asks its rung for several candidates makes one dispatch per draw,
        and a key that named only the attempt would give every draw's row one
        id, so a correction could reach only the last. The first draw is left
        unsuffixed: rows a journal already holds carry keys with no draw, and a
        correction finds its row by that key.
        """
        who = f"{self.orchestrator}:{self.run}" if self.run else self.orchestrator
        row = f"{who}:{contract}:{rung}:{attempt}"
        return row if draw == 0 else f"{row}#{draw}"
