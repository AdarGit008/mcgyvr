def draw_tree_lines(root):
    def inspect(node):
        name = node.get("name")
        if not isinstance(name, str) or name == "":
            raise ValueError("every node needs a non-empty string name")
        if "\n" in name:
            raise ValueError("a name may not span lines")
        if not isinstance(node.get("children"), list):
            raise ValueError("children must be a list")

    lines = []

    def sketch(nodes, indent):
        for position, node in enumerate(nodes):
            last = position == len(nodes) - 1
            inspect(node)
            lines.append(indent + ("'-- " if last else "|-- ") + node["name"])
            sketch(node["children"], indent + ("    " if last else "|   "))

    inspect(root)
    lines.append(root["name"])
    sketch(root["children"], "")
    return lines
