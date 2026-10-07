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

Nothing here opens a socket. The online half (the Hub, a header read over
HTTP ``Range``, the boards) answers records of this same type and files them
with :func:`mcgyvr.knowledge.store.write`; the offline read never knows which
run wrote the cache.
"""
