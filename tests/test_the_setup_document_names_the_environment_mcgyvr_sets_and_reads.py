"""SETUP.md names the environment mcgyvr sets and reads beyond its own folders.

`$MCGYVR_ENDPOINTS` is set in every task container that has a network, the
Hugging Face token and mirror variables are read for the Hub, and the rig
reader's `MCGYVR_TEST_*` hooks are for mcgyvr's own tests. docgen spells each
name once for the setup text; this holds every spelling to the constant the
code reads, so a rename there fails here until the document follows.
"""

from __future__ import annotations

from mcgyvr import docgen
from mcgyvr.sandbox import docker
from mcgyvr.serving import fetchlist, rigscan
from tests._paths import REPO

SETUP_MD = REPO / "skills" / "mcgyvr" / "SETUP.md"


def test_each_name_is_the_one_its_reader_uses() -> None:
    assert docgen.ENDPOINTS_ENV == docker.ENDPOINTS_ENV
    assert docgen.HOST_ALIAS == docker.HOST_ALIAS
    assert docgen.HF_TOKEN_ENV == fetchlist.DEFAULT_TOKEN_ENV
    assert docgen.HF_ENDPOINT_ENV == fetchlist.ENDPOINT_ENV
    for hook in (
        rigscan.ROOT_VARIABLE,
        rigscan.SECONDS_VARIABLE,
        rigscan.SYSTEM_VARIABLE,
    ):
        assert hook.startswith(docgen.TEST_ENV_PREFIX)


def test_the_setup_document_names_each_one() -> None:
    text = " ".join(SETUP_MD.read_text(encoding="utf-8").split())
    assert f"mcgyvr sets `${docker.ENDPOINTS_ENV}` in every task container" in text
    assert f"`${fetchlist.DEFAULT_TOKEN_ENV}`" in text
    assert f"`${fetchlist.ENDPOINT_ENV}` names a mirror" in text
    assert f"`{docgen.TEST_ENV_PREFIX}*` variables" in text
