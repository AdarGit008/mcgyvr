"""One symbol extractor per language, and the tree-sitter engine they share.

:mod:`mcgyvr.orchestrator.symbols` dispatches a path to one of these by suffix and is
the module callers import. Each language module states its own rules (what is a
definition, what is exported, how an import is named) in its docstring and exposes
``SUFFIXES`` and ``extract(path, source)``; the record they all emit is
:mod:`~mcgyvr.orchestrator.languages.model`.
"""
