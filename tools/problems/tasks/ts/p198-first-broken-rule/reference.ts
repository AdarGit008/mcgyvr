type Node = {
  key: number;
  count: number;
  left: Node | null;
  right: Node | null;
};

type Stats = { depth: number; size: number; keys: number[] };

function validate(raw: unknown, where: string): Node | null {
  if (raw === null || raw === undefined) {
    return null;
  }
  if (typeof raw !== "object" || Array.isArray(raw)) {
    throw new Error(where + " is neither a node nor nothing");
  }
  const node = raw as Record<string, unknown>;
  for (const entry of ["key", "count", "left", "right"]) {
    if (!(entry in node)) {
      throw new Error(where + " lacks the entry " + entry);
    }
  }
  if (!Number.isInteger(node.key)) {
    throw new Error(where + " has a key that is not a whole number");
  }
  if (!Number.isInteger(node.count) || (node.count as number) <= 0) {
    throw new Error(where + " has a count that is not a positive whole number");
  }
  validate(node.left, where + "/L");
  validate(node.right, where + "/R");
  return node as unknown as Node;
}

function stats(node: Node | null): Stats {
  if (node === null || node === undefined) {
    return { depth: 0, size: 0, keys: [] };
  }
  const left = stats(node.left);
  const right = stats(node.right);
  return {
    depth: 1 + Math.max(left.depth, right.depth),
    size: 1 + left.size + right.size,
    keys: [node.key, ...left.keys, ...right.keys],
  };
}

function inspect(node: Node, path: string): Record<string, string> | null {
  const left = stats(node.left ?? null);
  const right = stats(node.right ?? null);
  if (
    left.keys.some((key) => key >= node.key) ||
    right.keys.some((key) => key <= node.key)
  ) {
    return { path, rule: "order" };
  }
  if (Math.abs(left.depth - right.depth) > 1) {
    return { path, rule: "balance" };
  }
  if (node.count !== 1 + left.size + right.size) {
    return { path, rule: "count" };
  }
  if (node.left !== null && node.left !== undefined) {
    const below = inspect(node.left, path + "/L");
    if (below !== null) {
      return below;
    }
  }
  if (node.right !== null && node.right !== undefined) {
    const below = inspect(node.right, path + "/R");
    if (below !== null) {
      return below;
    }
  }
  return null;
}

export function firstBrokenRule(
  root: Record<string, unknown>
): Record<string, string> {
  const node = validate(root, "root");
  if (node === null) {
    throw new Error("there is no root to inspect");
  }
  return inspect(node, "root") ?? { path: "", rule: "sound" };
}
