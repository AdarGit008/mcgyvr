"""The fleet file readers: the package's public surface for fleet and policy.

This module holds no logic of its own. It re-exports `FleetFileError`,
`load_fleet` and `load_policy` from `mcgyvr.fleet.files` and names them in
`__all__`, so a caller can load the two files that describe a fleet from one
import.

`load_fleet(text)` reads the text of a `fleet.yaml` and returns its `units`,
`rigs` and `fleets` blocks, raising `FleetFileError` for a key that belongs in
another file, is retired, or is unknown. `load_policy(text)` reads the text of
a `policy.yaml` and returns its `ladder` — an ordered list of unit names — with
the policy settings alongside it, raising `FleetFileError` for a unit fact or
an unknown key. Both refuse a `relief` block, which belongs in `relief.yaml`.
"""

from mcgyvr.fleet.files import FleetFileError, load_fleet, load_policy

__all__ = ["FleetFileError", "load_fleet", "load_policy"]
