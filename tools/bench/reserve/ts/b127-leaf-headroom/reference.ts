/** Spendable request units per leaf of a nested quota-group tree. */

function checkCount(value: unknown, what: string): number {
  if (typeof value !== "number" || !Number.isInteger(value) || value < 0) {
    throw new Error(`${what} must be a non-negative integer`);
  }
  return value;
}

function isNode(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function burnOf(node: unknown, burns: Map<unknown, number>): number {
  if (!isNode(node)) {
    throw new Error("a node must be a plain object");
  }
  checkCount(node.limit, "limit");
  let total = 0;
  if (!("children" in node)) {
    total = checkCount(node.used, "a leaf's used");
  } else {
    if ("used" in node) {
      throw new Error("a group must not carry used");
    }
    if (!isNode(node.children)) {
      throw new Error("children must map names to nodes");
    }
    for (const [name, child] of Object.entries(node.children)) {
      if (name === "") {
        throw new Error("a child name must not be empty");
      }
      if (name.includes("/")) {
        throw new Error(`a child name must not hold a slash: ${name}`);
      }
      total += burnOf(child, burns);
    }
  }
  burns.set(node, total);
  return total;
}

function collect(
  node: any,
  path: string,
  ceiling: number,
  burns: Map<unknown, number>,
  into: Record<string, number>,
): void {
  const room = Math.min(ceiling, node.limit - (burns.get(node) ?? 0));
  if (!("children" in node)) {
    into[path] = Math.max(0, room);
    return;
  }
  for (const [name, child] of Object.entries(node.children)) {
    collect(child, path === "" ? name : `${path}/${name}`, room, burns, into);
  }
}

export function leafHeadroom(tree: unknown): Record<string, number> {
  if (!isNode(tree) || !("children" in tree)) {
    throw new Error("the root must be a quota group");
  }
  const burns = new Map<unknown, number>();
  burnOf(tree, burns);
  const into: Record<string, number> = {};
  collect(tree, "", Infinity, burns, into);
  return into;
}
