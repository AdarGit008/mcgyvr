def crust_slice(name: str) -> str:
    cut = name.rfind(".")
    if cut <= 0:
        return name
    return name[:cut]
