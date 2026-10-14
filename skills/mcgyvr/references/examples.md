<!-- Code generated from src/mcgyvr/contract.py and src/mcgyvr/docgen.py by `make docs`. DO NOT EDIT. -->

# One minimal `code` contract, and one per deterministic operation

Each loads through the contract validator; they are checked by the test
suite, so copying one is copying a shape that is known to validate. The
keys are documented in `SKILL.md`.

## A change a model makes

### `code`

```yaml
id: impl-chunk
task_type: code
task: >-
  Implement chunk. Split a list into consecutive groups of at most size
  elements, preserving order; the last group is shorter when the length does
  not divide evenly. An empty list yields an empty list. Raise ValueError
  unless size is a positive integer.
target: src/pkg/chunk.py
interface: "def chunk(items: list[T], size: int) -> list[list[T]]"
stop_conditions:
  - Whether a size larger than the list is an error or one group is not stated.
demonstration: ["pytest -q tests/test_chunk.py"]
risk: low
limits:
  max_output_tokens: 4096
scope:
  allow: ["src/pkg/chunk.py"]
```

## Deterministic operations (`task_type: code` with `operation:`)

### `format`

```yaml
id: format-pkg
task_type: code
operation: format
task: Reformat the module with the project's formatter.
target: src/pkg/messy.py
scope:
  allow: ["src/pkg/**"]
```

### `import_sort`

```yaml
id: sort-imports
task_type: code
operation: import_sort
task: Order the module's imports with the project's import sorter.
target: src/pkg/messy.py
scope:
  allow: ["src/pkg/**"]
```

### `lint_fix`

```yaml
id: lint-pkg
task_type: code
operation: lint_fix
task: Apply the linter's own autofixes to the module.
target: src/pkg/messy.py
scope:
  allow: ["src/pkg/**"]
```

### `rename_symbol`

```yaml
id: rename-fetch
task_type: code
operation: rename_symbol
task: Rename fetch_page to fetch_document in the module.
target: src/pkg/messy.py
rename:
  from: fetch_page
  to: fetch_document
scope:
  allow: ["src/pkg/**"]
```
