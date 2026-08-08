def process_stock_moves(moves: list) -> dict:
    levels = {}
    refused = []
    for index, move in enumerate(moves):
        op = move.get("op")
        item = move.get("item")
        qty = move.get("qty")
        if op not in ("receive", "issue", "recount"):
            raise ValueError(f"unknown op at move {index}")
        if not isinstance(item, str) or item == "":
            raise ValueError(f"bad item at move {index}")
        if not isinstance(qty, int) or isinstance(qty, bool):
            raise ValueError(f"qty must be an integer at move {index}")
        if op in ("receive", "issue") and qty < 1:
            raise ValueError(f"qty below 1 at move {index}")
        if op == "recount" and qty < 0:
            raise ValueError(f"recount below 0 at move {index}")
        if op == "receive":
            levels[item] = levels.get(item, 0) + qty
        elif op == "recount":
            levels[item] = qty
        elif item not in levels:
            refused.append([index, "unknown_item"])
        elif levels[item] < qty:
            refused.append([index, "short"])
        else:
            levels[item] -= qty
    return {"levels": levels, "refused": refused}
