"""mcgyvr command line — a package after the split of cli.py.

Re-exports the two public entrypoint names, plus the private names the old
``cli.py`` exposed and the test suite still reads off the package. The
monkeypatched names are repointed in the tests themselves; these re-exports
serve plain attribute access only.
"""

from mcgyvr.cli.dispatcher import build_parser, hanging_up_on_interrupt, main
from mcgyvr.cli.common import CONFIG_DEFAULT_HELP, SETUP_DOC
from mcgyvr.cli.sizing import _model_spec, _model_specs, _resolve_hosts
from mcgyvr.cli.commands.setup import (
    _SetupInteractiveError,
    _read_rig,
    _rig_id,
    _setup_context_window,
    _setup_downloads,
    _setup_emit,
    _setup_fetch,
    _setup_is_interactive,
    _setup_on_disk_match,
    _setup_pick_unit,
    _setup_placements,
    _setup_scan_rigs,
    _setup_start,
)
from mcgyvr.cli.commands.run import (
    DELIVERY_REFUSED,
    NOTHING_TO_CHANGE,
    _climb,
    _error,
    _floor,
    _name_the_writer,
    _ran,
    _report_climb,
    _report_run,
)
from mcgyvr.cli.commands.ladder import _emit, _manage_held
from mcgyvr.cli.commands.delegate import _proposer_for_delegate

__all__ = ["build_parser", "main"]
