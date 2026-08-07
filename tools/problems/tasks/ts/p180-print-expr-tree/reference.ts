const BINDING: Record<string, number> = { "+": 1, "-": 1, "*": 2, "/": 2 };
const ATOM = 3;

function binding(node: any): number {
  if (typeof node === "number" || typeof node === "string") {
    return ATOM;
  }
  return BINDING[node.op];
}

function render(node: any): string {
  if (typeof node === "number") {
    if (!Number.isInteger(node) || node < 0) {
      throw new Error("a literal must be a whole number of zero or more");
    }
    return String(node);
  }
  if (typeof node === "string") {
    if (!/^[A-Za-z]+$/.test(node)) {
      throw new Error("a name must be a non-empty run of letters");
    }
    return node;
  }
  if (typeof node !== "object" || node === null || Array.isArray(node)) {
    throw new Error("a node must be a number, a string or a record");
  }
  if (!("op" in node) || !("left" in node) || !("right" in node)) {
    throw new Error("a record needs op, left and right");
  }
  const power = BINDING[node.op];
  if (power === undefined) {
    throw new Error("the operator must be one of + - * /");
  }
  const leftText = render(node.left);
  const rightText = render(node.right);
  const left = binding(node.left) < power ? "(" + leftText + ")" : leftText;
  const right = binding(node.right) <= power ? "(" + rightText + ")" : rightText;
  return left + " " + node.op + " " + right;
}

export function printExprTree(node: unknown): string {
  return render(node);
}
