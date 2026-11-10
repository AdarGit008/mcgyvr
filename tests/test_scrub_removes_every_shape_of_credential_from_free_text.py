"""`redact.scrub` removes every shape of credential a model may leave in free text.

`scrub` is the one cleaner telemetry, notes and the sandbox call, so a key that
survives it reaches a journal blob, a failure note shared with another user, or a
command's environment. It removes, by pattern: a URL's `user:token@` userinfo, a
`Bearer` authorization token, a pasted private key from header to footer, and
every provider token shape of the shared vocabulary (`credential_shapes`). Text
that holds no credential comes back unchanged, which is how callers test for one.

The Bearer and private-key cases are pinned sharply because each had a sharp
edge: the Bearer match must not cross a newline (it would join two stored lines)
and must be case-insensitive (the HTTP scheme is), and the private-key pass must
take the base64 body, not only the header line the gate's shape matches.
"""

from __future__ import annotations

from mcgyvr.redact import REDACTED, scrub


def test_a_url_userinfo_is_redacted_and_the_host_kept() -> None:
    assert scrub("see https://me:hunter2@host.example/v1 now") == (
        f"see https://{REDACTED}@host.example/v1 now"
    )


def test_each_provider_token_shape_is_blanked() -> None:
    assert scrub("key sk-abcdef0123456789ABCDEF end") == f"key {REDACTED} end"
    assert scrub("tok ghp_" + "a" * 36) == f"tok {REDACTED}"
    assert scrub("id AKIAIOSFODNN7EXAMPLE end") == f"id {REDACTED} end"


def test_a_bearer_token_is_blanked_but_its_word_and_spacing_are_kept() -> None:
    assert (
        scrub("Authorization: Bearer eyJ.a.b-c") == f"Authorization: Bearer {REDACTED}"
    )


def test_a_bearer_match_is_case_insensitive() -> None:
    # curl examples lower-case the scheme; the HTTP auth scheme is case-insensitive.
    assert scrub("authorization: bearer abc.def") == f"authorization: bearer {REDACTED}"


def test_a_bearer_match_never_crosses_a_newline() -> None:
    # "Bearer" at a line end with the token on the next line is not a header; the
    # next line's first word must survive and the lines must not be joined.
    assert scrub("the Bearer\nnext line") == "the Bearer\nnext line"


def test_a_pasted_private_key_is_taken_whole_header_to_footer() -> None:
    pem = (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIEbody123\nMORE456\n"
        "-----END RSA PRIVATE KEY-----"
    )
    assert scrub(pem) == REDACTED


def test_a_private_key_with_its_footer_cut_is_taken_to_the_end_of_text() -> None:
    pem = "pasted:\n-----BEGIN PRIVATE KEY-----\nMIIEbody\n"
    assert scrub(pem) == f"pasted:\n{REDACTED}"


def test_text_with_no_credential_comes_back_unchanged() -> None:
    # An IP:port and a bare assignment are not credentials; compare-to-detect
    # relies on an unaltered return meaning "no secret here".
    clean = "reach 198.51.100.2:51820, then VALUE = 1 in src/pkg/x.py"
    assert scrub(clean) == clean


def test_scrub_is_idempotent() -> None:
    once = scrub("key sk-abcdef0123456789ABCDEF and Bearer eyJ.a.b")
    assert scrub(once) == once
