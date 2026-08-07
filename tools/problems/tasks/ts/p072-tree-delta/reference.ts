type TreeNode = { name: string; value: number; children: TreeNode[] };

function assertSiblings(node: TreeNode): void {
  const seen = new Set<string>();
  for (const child of node.children) {
    if (seen.has(child.name)) {
      throw new Error("duplicate sibling name: " + child.name);
    }
    seen.add(child.name);
    assertSiblings(child);
  }
}

function addAll(
  node: TreeNode,
  path: string,
  out: Array<Record<string, unknown>>
): void {
  out.push({ op: "add", path, value: node.value });
  for (const child of node.children) {
    addAll(child, path + "/" + child.name, out);
  }
}

function walk(
  before: TreeNode,
  after: TreeNode,
  path: string,
  out: Array<Record<string, unknown>>
): void {
  if (before.value !== after.value) {
    out.push({ op: "change", path, from: before.value, to: after.value });
  }
  const olds = new Map(before.children.map((c) => [c.name, c]));
  const kept = new Set(after.children.map((c) => c.name));
  for (const child of after.children) {
    const childPath = path + "/" + child.name;
    const prior = olds.get(child.name);
    if (prior !== undefined) {
      walk(prior, child, childPath, out);
    } else {
      addAll(child, childPath, out);
    }
  }
  for (const child of before.children) {
    if (!kept.has(child.name)) {
      out.push({ op: "remove", path: path + "/" + child.name });
    }
  }
}

export function treeDelta(
  before: { name: string; value: number; children: unknown[] },
  after: { name: string; value: number; children: unknown[] }
): Array<Record<string, unknown>> {
  const b = before as TreeNode;
  const a = after as TreeNode;
  if (b.name !== a.name) {
    throw new Error("root names differ");
  }
  assertSiblings(b);
  assertSiblings(a);
  const out: Array<Record<string, unknown>> = [];
  walk(b, a, b.name, out);
  return out;
}
