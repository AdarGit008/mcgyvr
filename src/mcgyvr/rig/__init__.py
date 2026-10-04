"""This machine as a rig of a hub: joined, described, and kept in touch.

A hub is where users publish their machines and pool them; a rig is one
machine published there. ``mcgyvr rig join`` keeps the rig token the hub gave
the user, opens the hub's agent channel (a websocket), says ``hello`` with this
machine's hardware as the product reads it, and then sends heartbeats until it
is stopped, reconnecting with backoff when the channel drops.

* :mod:`mcgyvr.rig.protocol` — the hub's wire protocol, version 1: the limits
  the agent needs, reading a hub frame, writing an agent frame.
* :mod:`mcgyvr.rig.websocket` — a websocket client on the standard library.
* :mod:`mcgyvr.rig.hardware` — the hardware report, from the product's own
  machine reading.
* :mod:`mcgyvr.rig.credentials` — where the rig token is kept, and how.
* :mod:`mcgyvr.rig.commands` — what the agent does with each message the hub
  sends; the seam later commands are added at.
* :mod:`mcgyvr.rig.agent` — the session, the heartbeats and the reconnects.
* :mod:`mcgyvr.rig.verbs` — ``mcgyvr rig join | run | status | leave | rungs |
  share``.
* :mod:`mcgyvr.rig.rungs` — the relief rungs the hub matched this rider to,
  kept in ``relief.yaml``.

A rig may lend its cards to the hub's pooled-inference sessions:

* :mod:`mcgyvr.rig.sharing` — what the owner lends, and where that is kept.
* :mod:`mcgyvr.rig.inventory` — the models it can serve, named, never pathed.
* :mod:`mcgyvr.rig.sessionwire` — the session and relay messages.
* :mod:`mcgyvr.rig.tunnel` — which addresses a session's tunnel may use.
* :mod:`mcgyvr.rig.session` — one state machine per session, and teardown.
* :mod:`mcgyvr.rig.tensorcache` — the workers' tensor cache, hashed before
  it is mounted.
* :mod:`mcgyvr.rig.relay` — a relayed request to the head, and its answer.
* :mod:`mcgyvr.rig.outbox` — what sessions and relays say, waiting its turn.

Their containers are :mod:`mcgyvr.sandbox.pooled`'s.

A rig here is a machine on a hub. It is not the ``rigs`` of a ``fleet.yaml``,
which name machines a fleet's units are served on; the two meet only when the
same machine is both.
"""
