"""S11 — an unsupported output schema is refused before the dispatch, not after it.

A contract can declare ``output_schema: unified_diff``, and the loader accepts it
— but the prompt builder has no reply instruction for it and the reply parser
has no parser for it. The result is a prompt sent with no format instruction at
all, and a reply that is refused as unsupported only *after* a model call has
already been paid for.

The fix refuses the unsupported schema at prompt-build time, where the dispatch
has not happened and the cost is zero.
"""

from __future__ import annotations

from typing import Any

import pytest

from mcgyvr.contract import loads
from mcgyvr.worker.prompt import UnsupportedSchemaError, build_prompt

UNIFIED_DIFF = """
id: fetch-retry
task_type: function_implementation
task: Add retry with backoff to the fetch helper.
target: src/pkg/fetch.py
output_schema: unified_diff
stop_conditions:
  - The retry policy is not stated anywhere in the repo.
acceptance: ["python -c 'import sys; sys.exit(0)'"]
scope:
  allow: ["src/**/*.py"]
"""


def test_a_unified_diff_contract_is_refused_before_dispatch() -> None:
    """The unsupported shape is named at build time, with no model asked."""
    contract: Any = loads(UNIFIED_DIFF)

    with pytest.raises(UnsupportedSchemaError, match="unified_diff"):
        build_prompt(contract)
