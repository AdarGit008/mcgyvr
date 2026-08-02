# ghostcall

> Detect hallucinated API calls in LLM-generated Python code.

[![CI](https://github.com/linosorice/ghostcall/actions/workflows/ci.yml/badge.svg)](https://github.com/linosorice/ghostcall/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/ghostcall)](https://pypi.org/project/ghostcall/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

LLMs invent methods that don't exist. `ghostcall` parses Python code, looks at the packages you actually have installed, and tells you which calls are real and which are phantoms.

![demo](https://raw.githubusercontent.com/linosorice/ghostcall/main/demo.gif)

## Install

```bash
pip install ghostcall
```

Requires Python 3.9+.

## Quickstart

```bash
# Check a file
ghostcall path/to/llm_output.py

# Pipe from stdin (your favorite use case for ChatGPT output)
pbpaste | ghostcall

# Extract Python from a markdown file (e.g., LLM chat exports)
ghostcall --md chat.md
```

## Why this tool?

Every developer who has used Copilot or ChatGPT has pasted code with a method that doesn't exist and lost 20 minutes debugging. Linters check *your* code — nothing checks generated code against the packages you actually have installed.

`ghostcall` fills that gap. Pipe in code, get back a list of phantom calls and suggestions.

It's not `mypy` or `pyright`: those check types and need a full project context. `ghostcall` checks *existence* and works on any snippet, in isolation.

## Examples

### Catch hallucinated method names

```bash
$ echo 'import pandas as pd
pd.DataFrame.to_jsonl()' | ghostcall

  ⚠ pd.DataFrame.to_jsonl() does not exist
    line 2  →  Did you mean to_json, to_sql?

✗ Found 1 hallucinated call
```

### Catch hallucinated functions on real modules

```bash
$ echo 'import requests
requests.get_async("https://api.example.com")' | ghostcall

  ⚠ requests.get_async() does not exist
    line 2

✗ Found 1 hallucinated call
```

### Check Python blocks inside markdown

If you save your ChatGPT conversation as `.md`, just point `ghostcall` at it:

```bash
$ ghostcall --md chatgpt_export.md
```

Only fenced ```python code blocks are checked. Other languages and prose are ignored.

### Machine-readable output for CI

```bash
$ ghostcall --json output.py
{
  "source": "output.py",
  "summary": {
    "total_calls_checked": 5,
    "hallucinations_found": 1,
    "module_missing": 0,
    "dynamic_skipped": 0,
    "ok": 4
  },
  "findings": [
    {
      "type": "hallucinated",
      "line": 2,
      "col": 0,
      "call": "pd.DataFrame.to_jsonl",
      "resolved": "pandas.DataFrame.to_jsonl",
      "missing_attr": "to_jsonl",
      "parent": "pandas.DataFrame",
      "suggestions": ["to_json", "to_sql"]
    }
  ]
}
```

Exit codes: `0` clean, `1` hallucinations found, `2` syntax error in input.

## How it works

1. Parse the Python source with the standard `ast` module.
2. Build an alias map from imports (`import pandas as pd` → `pd → pandas`).
3. For each dotted call chain (`pd.DataFrame.to_jsonl`), resolve it through the alias map and walk it through the *actually installed* package via `importlib` + `getattr`.
4. If an attribute is missing, suggest close matches via `difflib`.

Because it checks against your real environment, the answers reflect the exact version of the package you have.

## Limitations

<details>
<summary>What ghostcall does NOT do</summary>

- **No type checking** — that's `mypy` / `pyright`. ghostcall only checks *existence*.
- **No data-flow analysis** — `df = pd.DataFrame(); df.fake_method()` is not caught because `df` is a local variable. Direct chains from imports only.
- **No support for `import *`** — wildcard imports are skipped with a warning.
- **No support for non-Python languages.**
- **No auto-fix.**
- **Modules with `__getattr__` magic** (e.g., some ORMs) are skipped to avoid false positives.

</details>

## Contributing

Issues and PRs welcome. The codebase is small (~330 lines) and built on stdlib (`ast`, `importlib`, `difflib`). The four files that matter:

- `src/ghostcall/parser.py` — AST visitor, import resolution
- `src/ghostcall/checker.py` — introspection against installed packages
- `src/ghostcall/suggest.py` — fuzzy matching
- `src/ghostcall/output.py` — terminal and JSON rendering

Run tests with:

```bash
pip install -e ".[dev]"
pytest
```

## License

MIT — see [LICENSE](LICENSE).
