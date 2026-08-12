def rota_next(rota: list, name: str) -> str:
    if name not in rota:
        return name
    return rota[(rota.index(name) + 1) % len(rota)]
