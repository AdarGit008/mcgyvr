"""Where a run's attempt records go, and which orchestrator is writing them.

`Recording` is the value the driver hands to `telemetry.observe` for every
dispatch and to `telemetry.correct` for every row it corrects afterwards: the
journal sink, the orchestrator id the rows are filed under, the run stamp, the
session transcript and any copies the caller asked for. `attempt_id` is what
those rows are keyed by, and `copy_failed` collects a copy that could not be
written instead of raising it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Recording:
    """Where one run's records go, and who is writing them.

    `path` is the JSONL sink the rows are appended to, `orchestrator` the id
    every row is filed under, and `run` this run's stamp — empty when the caller
    made none, and the ids then name the orchestrator alone. A recording is
    built once per run, and the driver reads it to reach the sink rather than to
    open it: nothing here writes, and the journal directory is not created.
    """

    path: Path
    orchestrator: str
    run: str = ""
    # `session_file` is the transcript of the session that typed the command, so
    # a row can be followed back to the conversation that produced it:
    # `observe` writes it into the row's identity, and `None` means no session
    # named one.
    session_file: Path | None = None
    # `mirrors` are further directories this run's record is written into, for a
    # caller that asked for a copy — `--record DIR` when it is not the journal
    # directory itself. They are copies and not sinks: the record under `path`
    # is written first and is complete whatever happens here, so a mirror that
    # cannot be written is reported through `copy_failed` and the run goes on.
    # Empty on almost every run, which is what makes a non-empty `copy_errors`
    # worth reading.
    mirrors: tuple[Path, ...] = ()
    # `copy_errors` is the mirrors that could not be written, keyed by the
    # mirror directory and holding `"<ExcType>: <message>"`. It is filled by
    # `copy_failed` when a copy raises, and never raised from here. `compare`
    # of `False` keeps it out of equality: a copy that failed does not make this
    # a different recording of the same run, and comparing a dict a caller can
    # still fill would compare state rather than identity. Empty on almost every
    # run; the CLI copies it into the result file and says each failure on
    # stderr, so a lost copy is neither silent nor a reason to stop.
    copy_errors: dict[Path, str] = field(default_factory=dict, compare=False)

    def copy_failed(self, mirror: Path, exc: BaseException) -> None:
        """Record that this run's record could not be copied to `mirror`.

        `mirror` is the directory the copy was meant for and `exc` the failure
        that stopped it, kept as `"<ExcType>: <message>"`. Only the first
        failure per mirror is kept; a later one leaves it unchanged. Nothing is
        raised: a copy is not a sink.
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
        """The id this run records one dispatch under.

        Built as `[orchestrator:run:]contract:rung:attempt`, with the run stamp
        left out when `run` is empty, and suffixed `#<draw>` for a draw past the
        first. Draw `0` therefore carries the unsuffixed id an install without
        breadth already writes, and draws `1` and up get `#1`, `#2`, … of their
        own, so the rows of one attempt stay distinct without renumbering it.
        """
        who = f"{self.orchestrator}:{self.run}" if self.run else self.orchestrator
        row = f"{who}:{contract}:{rung}:{attempt}"
        return row if draw == 0 else f"{row}#{draw}"
