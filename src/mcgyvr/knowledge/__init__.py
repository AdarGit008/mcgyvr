"""What mcgyvr knows about a model, and where each number of it came from.

Owner, 2026-10-07: "Every number records its source and date. Offline falls
back to the shipped catalog."

* :mod:`mcgyvr.knowledge.record` is the record: a model's sizes, geometry and
  board scores, each number carrying its kind, its source and the day it was
  read, and the closed lists those are said from (the kinds, the sources, the
  boards).
* :mod:`mcgyvr.knowledge.store` is where records are kept and the order they
  are read in: the user's cache under ``$MCGYVR_HOME/knowledge/`` first, then
  the catalog shipped in the package (``data/model-catalog.json``).

* :mod:`mcgyvr.knowledge.geometry` is each file's header row, the one thing
  the serving sizer reads, kept per file at a revision with one source and
  one date for the whole row: the cache's, then the shipped ones.

* :mod:`mcgyvr.knowledge.online` is the online half: the Hub's model API, each
  GGUF file's header read over HTTP ``Range`` (never a weight), and the
  refresh a command runs, which files what it read in the cache with
  :func:`mcgyvr.knowledge.store.write`. ``--offline`` or ``HF_HUB_OFFLINE``
  asks it nothing.
* :mod:`mcgyvr.knowledge.boards` reads the public leaderboards into scores
  and orders records by them for a use case.

Only ``online`` and ``boards`` open a socket. The offline read never knows
which run wrote the cache.
"""
