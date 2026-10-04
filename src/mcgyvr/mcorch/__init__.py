"""mcorch: the orchestrator that is a model to its harness.

``orchestrator.type: mcorch`` makes a local rung the conversational agent. The
user's harness (Claude Code, pi) points at ``mcgyvr mcorch serve``, an Anthropic
Messages API address; behind it the rung holds the conversation, the ``jev``
unit answers every bounded decision, and the harness runs every tool — mcorch
executes nothing itself. Running a contract is the rung emitting the harness's
own tool calls (write the contract, ``mcgyvr contract``, ``mcgyvr run``), which
is the ``/mcgyvr`` skill's flow with the rung in the API-tier agent's seat.

Above the pool seam: this package names roles and asks :mod:`mcgyvr.runner`
and :mod:`mcgyvr.decision` to reach them; it never holds an endpoint.
"""
