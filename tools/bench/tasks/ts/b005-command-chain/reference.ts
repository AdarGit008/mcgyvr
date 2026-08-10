type OrgNode = { name: string; reports: OrgNode[] };

export function chainOfCommand(root: OrgNode, person: string): string[] {
  if (typeof person !== "string" || person.length === 0) {
    throw new Error("person must be a non-empty string");
  }
  const matches: string[][] = [];
  function walk(node: OrgNode, trail: string[]): void {
    if (typeof node.name !== "string" || node.name.length === 0) {
      throw new Error("every name must be a non-empty string");
    }
    const path = [...trail, node.name];
    if (node.name === person) {
      matches.push(path);
    }
    for (const child of node.reports) {
      walk(child, path);
    }
  }
  walk(root, []);
  if (matches.length === 0) {
    throw new Error("person is not in the chart");
  }
  if (matches.length > 1) {
    throw new Error("person appears more than once");
  }
  return matches[0];
}

export function headcount(root: OrgNode): number {
  let total = 1;
  for (const child of root.reports) {
    total += headcount(child);
  }
  return total;
}

export function widestTeam(root: OrgNode): number {
  let widest = root.reports.length;
  for (const child of root.reports) {
    widest = Math.max(widest, widestTeam(child));
  }
  return widest;
}
