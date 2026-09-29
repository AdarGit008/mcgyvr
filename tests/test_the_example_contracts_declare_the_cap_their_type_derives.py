"""Every example contract the product generates declares the cap its type derives.

The examples rendered into the skill are what an agent copies. A model contract
must declare ``limits.max_output_tokens``, and the figure the product offers as
the value to start from is :func:`mcgyvr.contract.output_cap` for the task type.
So an example states that figure, read from the derivation when the examples
are built, and follows the derivation when it changes: a number typed into the
example would be a second statement of the product's default, free to drift
from the first.
"""

from __future__ import annotations

import pytest

from mcgyvr import contract, docgen


def test_each_example_declares_the_cap_its_task_type_derives() -> None:
    """A model example states the derived cap; a deterministic one needs none."""
    examples = docgen.examples()
    assert examples, "the product generates no example contracts"
    for task_type, text in examples.items():
        loaded = contract.loads(text)
        assert loaded.task_type == task_type
        assert loaded.limits.max_output_tokens == contract.output_cap(task_type), (
            f"the {task_type} example carries a cap its type does not derive"
        )
        if not loaded.is_deterministic:
            assert loaded.max_output_tokens_declared, (
                f"the {task_type} example is executed by a model but declares "
                "no cap, so copying it gives a contract the CLI refuses"
            )


def test_the_examples_follow_the_derivation_when_it_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Change what the product derives, and the examples carry the new figure."""
    types = list(docgen.examples())
    # Invented per type and odd, so no value can be mistaken for a real cap
    # and no two types share one; small enough to fit the default prompt budget.
    invented = {name: 101 + 2 * i for i, name in enumerate(types)}

    def derive(name: str, *, new_file: bool = False) -> int:
        return invented[name]

    monkeypatch.setattr(contract, "output_cap", derive)

    for task_type, text in docgen.examples().items():
        loaded = contract.loads(text)
        assert loaded.limits.max_output_tokens == invented[task_type], (
            f"the {task_type} example did not follow the derivation it is "
            "generated from"
        )

    # The rendered examples file is built from the same derivation, so it
    # carries the invented figures too: under each model type's heading, the
    # cap line states that type's number.
    rendered = docgen.render_examples()
    for task_type, text in docgen.examples().items():
        if not contract.loads(text).max_output_tokens_declared:
            continue
        section = rendered.split(f"## `{task_type}`", 1)[1].split("\n## `", 1)[0]
        assert f"max_output_tokens: {invented[task_type]}\n" in section, (
            f"the rendered {task_type} example did not follow the derivation it "
            "is generated from"
        )
