"""Dotted outline labels for a nested document, "1.2 Heading" style."""


def number_sections(sections: list) -> list:
    if not isinstance(sections, list):
        raise ValueError("number_sections expects a list of sections")
    labels = []

    def walk(nodes, trail):
        for index, node in enumerate(nodes):
            if not isinstance(node, dict) or not isinstance(node.get("children"), list):
                raise ValueError("a section must be a mapping with a children list")
            heading = node.get("heading")
            if not isinstance(heading, str) or not heading:
                raise ValueError("a heading must be a non-empty string")
            label = trail + str(index + 1)
            labels.append(label + " " + heading)
            walk(node["children"], label + ".")

    walk(sections, "")
    return labels


def section_count(sections: list) -> int:
    return len(number_sections(sections))
