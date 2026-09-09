<!-- Code generated from src/mcgyvr/contract.py and src/mcgyvr/docgen.py by `make docs`. DO NOT EDIT. -->

# One minimal contract per task type

Each loads through the contract validator; they are checked by the test
suite, so copying one is copying a shape that is known to validate. The
keys are documented in `SKILL.md`.

## `format`

```yaml
id: format-pkg
task_type: format
task: Reformat the module with the project's formatter.
target: src/pkg/messy.py
scope:
  allow: ["src/pkg/**"]
```

## `import_sort`

```yaml
id: sort-imports
task_type: import_sort
task: Order the module's imports with the project's import sorter.
target: src/pkg/messy.py
scope:
  allow: ["src/pkg/**"]
```

## `lint_fix`

```yaml
id: lint-pkg
task_type: lint_fix
task: Apply the linter's own autofixes to the module.
target: src/pkg/messy.py
scope:
  allow: ["src/pkg/**"]
```

## `rename_symbol`

```yaml
id: rename-fetch
task_type: rename_symbol
task: Rename fetch_page to fetch_document in the module.
target: src/pkg/messy.py
rename:
  from: fetch_page
  to: fetch_document
scope:
  allow: ["src/pkg/**"]
```

## `docstring`

```yaml
id: doc-fetch
task_type: docstring
task: Write the docstring for fetch_document, stating what it returns on a 404.
target: src/pkg/fetch.py
interface: "def fetch_document(url: str, *, timeout_s: float = 5.0) -> str"
stop_conditions:
  - The 404 behaviour cannot be read from the code.
limits:
  max_output_tokens: 512
scope:
  allow: ["src/pkg/fetch.py"]
```

## `type_annotation`

```yaml
id: annotate-fetch
task_type: type_annotation
task: Add type annotations to fetch_document and its helpers.
target: src/pkg/fetch.py
stop_conditions:
  - A helper's return type cannot be determined from its callers.
acceptance: ["mypy src/pkg/fetch.py"]
limits:
  max_output_tokens: 1024
scope:
  allow: ["src/pkg/fetch.py"]
```

## `function_implementation`

```yaml
id: impl-chunk
task_type: function_implementation
task: >-
  Implement chunk. Split a list into consecutive groups of at most size
  elements, preserving order; the last group is shorter when the length does
  not divide evenly. An empty list yields an empty list. Raise ValueError
  unless size is a positive integer.
target: src/pkg/chunk.py
interface: "def chunk(items: list[T], size: int) -> list[list[T]]"
stop_conditions:
  - Whether a size larger than the list is an error or one group is not stated.
acceptance: ["pytest -q tests/test_chunk.py"]
risk: low
limits:
  max_output_tokens: 1024
scope:
  allow: ["src/pkg/chunk.py"]
```

## `test_scaffold`

```yaml
id: test-chunk
task_type: test_scaffold
task: Write tests for chunk covering the empty list, an exact division and a remainder.
target: tests/test_chunk.py
interface: "def chunk(items: list[T], size: int) -> list[list[T]]"
deps:
  - path: src/pkg/chunk.py
    signature: "def chunk(items: list[T], size: int) -> list[list[T]]"
stop_conditions:
  - The expected result for a remainder group is not stated.
acceptance: ["pytest -q tests/test_chunk.py"]
limits:
  max_output_tokens: 1024
scope:
  allow: ["tests/test_chunk.py"]
```

## `bug_fix`

```yaml
id: fix-chunk-remainder
task_type: bug_fix
task: chunk drops the final short group when the length does not divide evenly; keep it.
target: src/pkg/chunk.py
interface: "def chunk(items: list[T], size: int) -> list[list[T]]"
stop_conditions:
  - The demonstrating test does not fail on the current code.
demonstration: ["pytest -q tests/test_chunk.py -k remainder"]
acceptance: ["pytest -q tests/test_chunk.py"]
limits:
  max_output_tokens: 1024
scope:
  allow: ["src/pkg/chunk.py"]
```
