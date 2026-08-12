from solution import audit_menu


def leaf(label):
    return {"label": label, "items": []}


assert audit_menu({"label": "menu", "items": [{"label": "drinks", "items": [leaf("tea")]}]}, 3) == [], "a tidy menu earns no complaints"
assert audit_menu({"label": "menu", "items": [leaf("  ")]}, 3) == ["menu >   : blank label"], "a label of nothing but spaces is complained about"
assert audit_menu({"label": "menu", "items": [leaf("tea"), leaf("tea")]}, 3) == ["menu > tea: duplicate"], "only the later of two identical labels is complained about"
assert audit_menu({"label": "menu", "items": [{"label": "drinks", "items": [leaf("tea")]}]}, 1) == ["menu > drinks > tea: too deep"], "a node below the allowed depth is complained about"
assert audit_menu({"label": "menu", "items": [leaf("tea"), leaf("tea")]}, 0) == ["menu > tea: too deep", "menu > tea: duplicate", "menu > tea: too deep"], "a node's complaints come in their fixed order, node by node"
assert audit_menu(leaf("menu"), 0) == [], "a root on its own is neither a duplicate nor too deep"


def rejects(*args):
    try:
        audit_menu(*args)
    except Exception:
        return True
    return False


assert rejects(leaf("menu"), -1), "a negative max_depth is rejected"
print("ok")
