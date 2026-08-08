const POWER: Record<string, number> = {
  or: 1,
  and: 2,
  "+": 3,
  "-": 3,
  "*": 4,
  "/": 4,
  "^": 6,
};
const NEGATE = 5;
const ALONE = 9;

function record(node: any): boolean {
  return typeof node === "object" && node !== null && !Array.isArray(node);
}

function power(node: any): number {
  if (typeof node === "number" || typeof node === "string") {
    return ALONE;
  }
  if ("op" in node) {
    return POWER[node.op];
  }
  if ("negate" in node) {
    return NEGATE;
  }
  return ALONE;
}

function show(node: any): string {
  if (typeof node === "number") {
    if (!Number.isInteger(node) || node < 0) {
      throw new Error("a number must be whole and not negative");
    }
    return String(node);
  }
  if (typeof node === "string") {
    if (!/^[a-z]+$/.test(node)) {
      throw new Error("a word must be a non-empty run of lowercase letters");
    }
    return node;
  }
  if (!record(node)) {
    throw new Error("a node must be a number, a word or a record");
  }
  if ("op" in node) {
    if (!("left" in node) || !("right" in node)) {
      throw new Error("a record carrying op needs left and right");
    }
    const here = POWER[node.op];
    if (here === undefined) {
      throw new Error("the operator is outside the seven");
    }
    const rightward = node.op === "^";
    const leftText = show(node.left);
    const rightText = show(node.right);
    const leftPower = power(node.left);
    const rightPower = power(node.right);
    const left =
      leftPower < here || (leftPower === here && rightward)
        ? "(" + leftText + ")"
        : leftText;
    const right =
      rightPower < here || (rightPower === here && !rightward)
        ? "(" + rightText + ")"
        : rightText;
    return left + " " + node.op + " " + right;
  }
  if ("negate" in node) {
    const inner = node.negate;
    const text = show(inner);
    const doubled = record(inner) && "negate" in inner;
    if (power(inner) < NEGATE || doubled) {
      return "-(" + text + ")";
    }
    return "-" + text;
  }
  if ("call" in node) {
    if (typeof node.call !== "string" || !/^[a-z]+$/.test(node.call)) {
      throw new Error("a call word must be a run of lowercase letters");
    }
    if (!("args" in node) || !Array.isArray(node.args)) {
      throw new Error("a call needs a list under args");
    }
    const parts: string[] = [];
    for (const argument of node.args) {
      parts.push(show(argument));
    }
    return node.call + "(" + parts.join(", ") + ")";
  }
  throw new Error("a record must carry op, negate or call");
}

export function printOperatorTree(node: unknown): string {
  return show(node);
}
