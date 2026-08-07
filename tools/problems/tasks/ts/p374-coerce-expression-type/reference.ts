const TYPES = ["tally", "measure", "glyph", "flag", "void"];
const DEPTH_CAP = 12;

function isMapping(value: unknown): boolean {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function has(node: Record<string, unknown>, key: string): boolean {
  return Object.prototype.hasOwnProperty.call(node, key);
}

function fuse(left: string, right: string): string {
  if (left === "void" || right === "void") {
    throw new Error("a void cannot be fused");
  }
  if (left === "flag" || right === "flag") {
    throw new Error("a flag cannot be fused");
  }
  if (left === "glyph" || right === "glyph") {
    return "glyph";
  }
  return left === "measure" || right === "measure" ? "measure" : "tally";
}

function order(left: string, right: string): string {
  if (left === "void" || right === "void") {
    throw new Error("a void has no order");
  }
  if (left === "flag" || right === "flag") {
    throw new Error("a flag has no order");
  }
  if (left === "glyph" || right === "glyph") {
    if (left !== right) {
      throw new Error("a glyph has no order against a quantity");
    }
    return "flag";
  }
  return "flag";
}

function match(left: string, right: string): string {
  if (left === "void" || right === "void") {
    return "flag";
  }
  if (left === "flag" || right === "flag") {
    if (left !== right) {
      throw new Error("a flag matches nothing but another flag");
    }
    return "flag";
  }
  if (left === "glyph" || right === "glyph") {
    if (left !== right) {
      throw new Error("a glyph does not match a quantity");
    }
    return "flag";
  }
  return "flag";
}

function walk(node: unknown, depth: number): string {
  if (depth > DEPTH_CAP) {
    throw new Error("the expression nests deeper than " + DEPTH_CAP + " nodes");
  }
  if (!isMapping(node)) {
    throw new Error("every node must be a mapping");
  }
  const held = node as Record<string, unknown>;
  const leaf = has(held, "type");
  const branch = has(held, "op");
  if (leaf === branch) {
    throw new Error("a node carries either a type or an op, never both or neither");
  }
  if (leaf) {
    const name = held.type;
    if (typeof name !== "string" || TYPES.indexOf(name) === -1) {
      throw new Error("a leaf must name one of the five types");
    }
    return name;
  }
  const op = held.op;
  if (op !== "+" && op !== "<" && op !== "=") {
    throw new Error("an op must be one of +, < and =");
  }
  if (!has(held, "left") || !has(held, "right")) {
    throw new Error("a branch must carry a left and a right");
  }
  const left = walk(held.left, depth + 1);
  const right = walk(held.right, depth + 1);
  if (op === "+") {
    return fuse(left, right);
  }
  if (op === "<") {
    return order(left, right);
  }
  return match(left, right);
}

export function coerceExpressionType(node: Record<string, unknown>): string {
  return walk(node, 1);
}
