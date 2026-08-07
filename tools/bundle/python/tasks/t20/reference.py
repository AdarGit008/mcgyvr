def read_config(text: str) -> dict[str, str]:
    """Parse KEY=VALUE lines into a dict."""
    config: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            raise ValueError(f"malformed line: {line!r}")
        key, _, value = stripped.partition("=")
        key = key.strip()
        if not key:
            raise ValueError(f"empty key in line: {line!r}")
        config[key] = value.strip()
    return config
