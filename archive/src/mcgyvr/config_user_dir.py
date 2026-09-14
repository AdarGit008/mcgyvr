"""The user-level config directory ``~/.mcgyvr/config`` — superseded 2026-09-15.

Moved here from ``src/mcgyvr/config.py`` when live fleets became folders of
their own (owner, 2026-09-15: "~/.mcgyvr/fleets/<name>/   live can switch
between fleets runtime"; the old ``~/.mcgyvr/config`` is to "move to
~/.mcgyvr/fleets/ and rename"). A config is now ``$MCGYVR_CONFIG``, then the
working directory, then the live fleet folder ``~/.mcgyvr/live.json`` names,
and ``mcgyvr init`` with no path writes the override or the working
directory. Its only tests are
``archive/tests/test_the_user_config_lives_under_dot_mcgyvr.py``.
"""

from __future__ import annotations

from pathlib import Path

#: The user-level config directory (owner, 2026-09-05). A literal with `~` so
#: help text reads the same on every machine; expanded at the point of use.
#: This is the third and last place a config is looked for, after the
#: environment override and the working directory, and where `mcgyvr init`
#: writes when nobody names a path. `$XDG_CONFIG_HOME` is not consulted.
USER_CONFIG_DIR = "~/.mcgyvr/config"


def user_config_path() -> Path:
    """``~/.mcgyvr/config``, expanded against the current HOME."""
    return Path(USER_CONFIG_DIR).expanduser()
