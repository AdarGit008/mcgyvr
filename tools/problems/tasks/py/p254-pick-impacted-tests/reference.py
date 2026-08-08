def pick_impacted_tests(coverage: dict, edited: list[str]) -> list[str]:
    if not isinstance(coverage, dict):
        raise ValueError("the coverage table must be a table of test names")
    if not isinstance(edited, list):
        raise ValueError("the edited paths must be a list")
    for path in edited:
        if not isinstance(path, str):
            raise ValueError("every edited path must be a string")
    touched = set(edited)
    picked = []
    for name, paths in coverage.items():
        if name == "":
            raise ValueError("a test name cannot be empty")
        if not isinstance(paths, list):
            raise ValueError(f"coverage for {name} must be a list")
        if not paths:
            raise ValueError(f"coverage for {name} is empty")
        seen = set()
        for path in paths:
            if not isinstance(path, str):
                raise ValueError(f"coverage for {name} holds a non-string path")
            if path in seen:
                raise ValueError(f"coverage for {name} repeats {path}")
            seen.add(path)
        if not touched:
            continue
        blanket = len(paths) == 1 and paths[0] == "*"
        if blanket or any(path in touched for path in paths):
            picked.append(name)
    return sorted(picked)
