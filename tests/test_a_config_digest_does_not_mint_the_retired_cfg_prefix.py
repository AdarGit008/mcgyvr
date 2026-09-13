"""A config digest no longer mints the retired ``cfg-`` prefix.

RED. ``mcgyvr.config.DIGEST_PREFIX = "cfg-"`` (``src/mcgyvr/config.py:51``) and
``Config.digest()`` returns it, while ``mcgyvr.fleet.ids`` refuses ``cfg-`` as a
retired identity prefix (``fleet/ids.py:20``). The intent
(``records/plans/fleet-identity.md`` §1 and §12): the prefix is retired together
with ``Config.digest()``/``keep()``, so no code mints a digest the new identity
primitive refuses.
"""

from __future__ import annotations


def test_a_config_digest_does_not_mint_the_retired_cfg_prefix() -> None:
    from mcgyvr import config

    cfg = config.Config(path=None, data={}, sources={}, ladder=config.Ladder(tiers=()))
    assert not cfg.digest().startswith("cfg-"), (
        "a config digest must not mint the retired cfg- prefix "
        "(mcgyvr.fleet.ids refuses it)"
    )
