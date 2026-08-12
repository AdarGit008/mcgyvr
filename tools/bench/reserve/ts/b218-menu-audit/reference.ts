interface MenuNode { label: string; items: MenuNode[] }

/** Collect the complaints a café menu's shape earns, in walking order. */
export function auditMenu(root: MenuNode, maxDepth: number): string[] {
  if (!Number.isInteger(maxDepth) || maxDepth < 0) {
    throw new Error("maxDepth must be a whole number of at least 0");
  }
  const complaints: string[] = [];
  const visit = (node: MenuNode, above: string[], twin: boolean): void => {
    const trail = [...above, node.label].join(" > ");
    if (node.label.trim() === "") {
      complaints.push(trail + ": blank label");
    }
    if (twin) {
      complaints.push(trail + ": duplicate");
    }
    if (above.length > maxDepth) {
      complaints.push(trail + ": too deep");
    }
    const seen = new Set<string>();
    for (const item of node.items) {
      visit(item, [...above, node.label], seen.has(item.label));
      seen.add(item.label);
    }
  };
  visit(root, [], false);
  return complaints;
}
