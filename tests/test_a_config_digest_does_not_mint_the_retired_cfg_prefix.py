"""A config digest no longer mints the retired ``cfg-`` prefix.

``mcgyvr.config`` used to mint a ``cfg-`` prefixed identity through
``Config.digest()`` and file a copy of the setup through :func:`keep`, while
``mcgyvr.fleet.ids`` refuses ``cfg-`` as a retired identity prefix
(``fleet/ids.py:20``). The owner ruled the prefix is retired together with the
mechanism, not re-prefixed: ``Config.digest()``/``keep()``/``DIGEST_PREFIX``
are gone, so no live code mints a digest the identity primitive refuses
(``mcgyvr-lab/records/plans/fleet-identity.md`` §1 and §9). The retired code and the
tests that existed only to call it are kept under ``archive/``.
"""

from __future__ import annotations


def test_a_config_digest_does_not_mint_the_retired_cfg_prefix() -> None:
    from mcgyvr import config
    from mcgyvr.fleet import ids

    assert not hasattr(config, "DIGEST_PREFIX"), (
        "the retired cfg- prefix must not survive in mcgyvr.config"
    )
    assert not hasattr(config.Config, "digest"), (
        "Config.digest() minted the retired cfg- identity and must be gone"
    )
    assert not hasattr(config, "keep"), (
        "keep() filed a config under a cfg- digest and must be gone"
    )
    # The conflict is resolved toward the identity primitive: a cfg- digest is
    # still refused there, and there is no live producer of one.
    assert "cfg-" not in ids.IDENTITY_PREFIXES
