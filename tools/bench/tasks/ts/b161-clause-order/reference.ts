export function clauseOrder(a: string, b: string): number {
  const shape = /^(?:0|[1-9]\d*)(?:\.(?:0|[1-9]\d*))*$/;
  for (const mark of [a, b]) {
    if (typeof mark !== "string" || !shape.test(mark)) {
      throw new Error("malformed clause mark");
    }
  }
  const left = a.split(".").map(Number);
  const right = b.split(".").map(Number);
  for (let i = 0; i < Math.max(left.length, right.length); i++) {
    const x = left[i] ?? -1;
    const y = right[i] ?? -1;
    if (x !== y) {
      return x < y ? -1 : 1;
    }
  }
  return 0;
}
