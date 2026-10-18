"""The mcorch orchestrator rung, served to a harness as the Anthropic Messages API.

``mcgyvr mcorch serve`` binds a loaded config to the two seams the loop
dispatches through (:mod:`mcgyvr.mcorch.bind`), listens for Messages requests
(:mod:`mcgyvr.mcorch.serve`), answers each of them as one turn of
:func:`mcgyvr.mcorch.loop.respond` — classifying the request, offering the
orchestrator model the harness tools plus mcorch's own authoring tools and
answering the calls it keeps for itself — and journals the turn's
:class:`~mcgyvr.mcorch.loop.Trace` (:mod:`mcgyvr.mcorch.transcript`). The other
modules are what such a turn needs: the two shapes translated both ways
(:mod:`mcgyvr.mcorch.anthropic`), evidence gathered through the harness shell
(:mod:`mcgyvr.mcorch.evidence`), the refusal to edit the target of a still-open
contract (:mod:`mcgyvr.mcorch.guard`), the authoring strategies and the system
prompt they run on (:mod:`mcgyvr.mcorch.authoring`, :mod:`mcgyvr.mcorch.prompt`),
and the ``Rung`` and ``Jev`` callables those turns are wired to
(:mod:`mcgyvr.mcorch.wire`).
"""
