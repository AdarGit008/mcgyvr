"""Ask the hub for the units your crews lend you, and keep them written.

A crew unit is a unit of a crew you are in, served by the hub from its crew
pool. Unlike a relief rung it is a plain unit of the setup: a ladder step or a
role binds it by name, and every request to it names scope crew, so the hub
serves it from the crew pool and from nowhere else.

* :func:`read` validates the hub's model listing whole: each listed model must
  be a model name the crew pool serves (:func:`mcgyvr.hubwire.serving_pool`),
  listed once, with its ready units' slots; one entry that cannot be read
  refuses the answer.
* :func:`render` turns the listing into the ``crew`` block of ``crew.yaml``.
* :func:`sync` asks and writes with ``rungs sync``'s one fetch
  (:func:`mcgyvr.rig.rungs.ask`) and one writer (:func:`mcgyvr.rig.rungs.keep`).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from mcgyvr.hubwire import (
    API_ROOT,
    MAX_SLOTS,
    MODEL_NAME,
    MODEL_SLOTS,
    MODELS_PATH,
    POOL_CREW,
    SCOPE_CREW,
    SCOPE_HEADER,
    serving_pool,
)
from mcgyvr.rig.rungs import (
    CREW,
    MAX_RUNG_WIDTH,
    _refused,
    ask,
    hub_url,
    keep,
    load_setup,
)

#: What a crew unit's name in crew.yaml starts with: the hub's model follows.
NAME_PREFIX = "crew-"
#: Most models one answer may list.
MAX_MODELS = 64


@dataclass(frozen=True)
class Lent:
    """One model the hub serves you from your crews' pool, and how many of
    your requests it takes at once: the slots of all its ready units."""

    model: str
    width: int

    @property
    def name(self) -> str:
        """The unit's name in ``crew.yaml``: the prefix, then the model."""
        return f"{NAME_PREFIX}{self.model}"


def _width(raw: object, where: str) -> int:
    if not isinstance(raw, list) or len(raw) > MAX_RUNG_WIDTH:
        raise _refused(where, f"is not a list of at most {MAX_RUNG_WIDTH} counts")
    for index, slots in enumerate(raw):
        if isinstance(slots, bool) or not isinstance(slots, int):
            raise _refused(f"{where}[{index}]", "is not a whole number")
        if not 1 <= slots <= MAX_SLOTS:
            raise _refused(f"{where}[{index}]", f"is not between 1 and {MAX_SLOTS}")
    return max(1, min(sum(raw), MAX_RUNG_WIDTH))


def _lent(raw: object, where: str) -> Lent:
    if not isinstance(raw, dict):
        raise _refused(where, "is not an object")
    model = raw.get("id")
    if not isinstance(model, str) or not MODEL_NAME.fullmatch(model):
        raise _refused(f"{where}.id", "is outside the model pattern")
    pool = serving_pool(SCOPE_CREW, model)
    if pool != POOL_CREW:
        raise _refused(f"{where}.id", f"is served from the {pool} pool, not a crew's")
    return Lent(
        model=model, width=_width(raw.get(MODEL_SLOTS), f"{where}.{MODEL_SLOTS}")
    )


def read(document: object) -> tuple[Lent, ...]:
    """Validate the hub's model listing whole and return it, in its order.

    ``data`` must be a list of at most ``MAX_MODELS`` models, each named once.
    A model's width is the sum of its units' slots, at least one and at most
    ``MAX_RUNG_WIDTH``. One bad entry raises
    :class:`mcgyvr.rig.rungs.HubAnswerError` naming
    where it is, so no partial listing is ever returned.
    """
    if not isinstance(document, dict):
        raise _refused("the answer", "is not a JSON object")
    listed = document.get("data")
    if not isinstance(listed, list):
        raise _refused("data", "is not a list")
    if len(listed) > MAX_MODELS:
        raise _refused("data", f"lists more than {MAX_MODELS}")
    lent = tuple(_lent(raw, f"data[{index}]") for index, raw in enumerate(listed))
    seen: set[str] = set()
    for index, each in enumerate(lent):
        if each.model in seen:
            raise _refused(f"data[{index}].id", "is listed twice")
        seen.add(each.model)
    return lent


def render(lent: tuple[Lent, ...], address: str, key_env: str) -> str:
    """The ``crew.yaml`` text for one listing.

    Every model becomes a unit under ``crew``, keyed by its name and carrying
    the hub's ``address``, the model, the key variable's name, its width and
    scope crew. A header says a sync rewrites the file whole and that the
    crews' hosts can read the prompts sent to their units.
    """
    block = {
        each.name: {
            "address": address,
            "model": each.model,
            "api_key_env": key_env,
            "width": each.width,
            "scope": SCOPE_CREW,
        }
        for each in lent
    }
    header = (
        "# Written by `mcgyvr rig crew sync`, which rewrites it whole: an edit\n"
        "# here lasts until the next sync. Your crews' hosts can read the\n"
        "# prompts sent to their units.\n"
    )
    return header + yaml.safe_dump({"crew": block}, sort_keys=False)


def sync(
    folder: Path, hub: str, key: str, key_env: str
) -> tuple[tuple[Lent, ...], Path]:
    """Sync once: ask the hub what your crews lend, then write it beside the setup.

    The listing is asked for at ``MODELS_PATH`` under scope crew and written as
    ``crew.yaml`` by the writer ``rungs sync`` uses: a crew unit a step or a
    role binds that the hub no longer lists, or a listing the setup would
    refuse, leaves the file as it was. Returns the listing and the file.
    """
    setup = load_setup(folder, CREW)
    answer = ask(
        hub_url(hub, MODELS_PATH), hub, key, headers={SCOPE_HEADER: SCOPE_CREW}
    )
    lent = read(answer)
    target = keep(
        setup,
        CREW,
        render(lent, hub_url(hub, API_ROOT), key_env),
        held=setup.config.crew,
        listed={each.name for each in lent},
    )
    return lent, target
