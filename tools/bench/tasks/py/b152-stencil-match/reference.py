def matches_stencil(stencil: str, code: str) -> bool:
    if not isinstance(stencil, str) or not stencil:
        raise ValueError("matches_stencil expects a non-empty stencil string")
    if not isinstance(code, str):
        raise ValueError("matches_stencil expects a string code")
    if len(code) != len(stencil):
        return False
    for want, have in zip(stencil, code):
        if want == "#" and have not in "0123456789":
            return False
        if want == "@" and not ("a" <= have <= "z" or "A" <= have <= "Z"):
            return False
        if want not in "#@?" and have != want:
            return False
    return True
