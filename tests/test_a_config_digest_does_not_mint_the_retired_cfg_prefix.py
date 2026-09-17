"""A config digest does not mint the retired ``cfg-`` prefix.

``mcgyvr.fleet.ids`` refuses ``cfg-`` as a retired identity prefix
(``_RETIRED_PREFIXES``). The prefix is retired together with the mechanism, not
re-prefixed (owner ruling): ``mcgyvr.config`` has no ``Config.digest()``, no
``keep()`` and no ``DIGEST_PREFIX``, so no live code mints a digest the
identity primitive refuses (``mcgyvr-lab/records/plans/fleet-identity.md`` §1
and §9). The retired code is kept in ``mcgyvr-lab/archive/``.
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
