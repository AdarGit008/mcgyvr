"""No example contract the product generates pins a reply cap.

The examples rendered into the skill are what an agent copies. The `code`
example used to pin the cap its type derives, 1024, and on DeepSeek's reasoning
models that cap came back as an empty reply on both rungs: the reasoning spent
all of it before a line was written (the e2e run of 2026-10-13). A model
contract that states no cap is now sized at each attempt from the target it
changes (:func:`mcgyvr.contract.auto_reply_cap`), so the example states none,
and copying it gives a contract the CLI accepts.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr import contract, docgen
from tests import livejournal as lj


def test_no_example_pins_a_cap() -> None:
    """Every example loads with its cap left to the sizing, from its type's floor."""
    examples = docgen.examples()
    assert examples, "the product generates no example contracts"
    for name, text in examples.items():
        loaded = contract.loads(text)
        assert loaded.kind.name == name
        assert not loaded.max_output_tokens_declared, (
            f"the {name} example pins a cap, which a reasoning model can spend "
            "before it writes a line"
        )
        assert loaded.limits.max_output_tokens == contract.output_cap(
            loaded.task_type, operation=loaded.operation, evidence=loaded.evidence
        ), f"the {name} example sizes up from a floor its kind does not derive"


def test_the_rendered_examples_state_no_cap() -> None:
    assert "max_output_tokens" not in docgen.render_examples()


def test_the_model_example_is_accepted_as_written(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`mcgyvr contract` takes the `code` example, and says the cap is sized."""
    path = lj.make_contract(tmp_path / "impl.yaml", docgen.examples()["code"])

    assert lj.main(["contract", str(path)]) == 0
    assert "output cap sized from the target each attempt" in capsys.readouterr().out
