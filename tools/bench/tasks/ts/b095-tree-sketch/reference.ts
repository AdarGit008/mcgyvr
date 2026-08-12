interface PanelNode {
  name: string;
  children: PanelNode[];
}

export function drawTreeLines(root: PanelNode): string[] {
  const inspect = (node: PanelNode): void => {
    if (typeof node.name !== "string" || node.name === "") {
      throw new Error("every node needs a non-empty string name");
    }
    if (node.name.includes("\n")) {
      throw new Error("a name may not span lines");
    }
    if (!Array.isArray(node.children)) {
      throw new Error("children must be a list");
    }
  };
  const lines: string[] = [];
  const sketch = (nodes: PanelNode[], indent: string): void => {
    for (let i = 0; i < nodes.length; i++) {
      const node = nodes[i];
      const last = i === nodes.length - 1;
      inspect(node);
      lines.push(indent + (last ? "'-- " : "|-- ") + node.name);
      sketch(node.children, indent + (last ? "    " : "|   "));
    }
  };
  inspect(root);
  lines.push(root.name);
  sketch(root.children, "");
  return lines;
}
