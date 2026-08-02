"""Extract Python code blocks from markdown."""

import re

# Match fenced code blocks tagged as python or py (case-insensitive),
# capturing the body. Tolerates leading whitespace inside the fence.
_BLOCK = re.compile(r"```(?:python|py)\b[^\n]*\n(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_python(text: str) -> str:
    """Concatenate all Python code blocks from a markdown document.

    Returns an empty string if no Python blocks are found.
    """
    blocks = _BLOCK.findall(text)
    return "\n".join(b.rstrip() for b in blocks)
