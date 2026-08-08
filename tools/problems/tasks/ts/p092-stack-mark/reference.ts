export function canonicalStackMark(mark: string): string {
  if (typeof mark !== "string") {
    throw new Error("stack mark must be a string");
  }
  const m = /^([1-9])(?:-| +)?([nsewNSEW])(?:-| +)?(\d{1,3})$/.exec(mark);
  if (m === null) {
    throw new Error("malformed stack mark");
  }
  const stack = Number(m[3]);
  if (stack === 0) {
    throw new Error("stack number must be at least 1");
  }
  return m[1] + m[2].toUpperCase() + String(stack).padStart(3, "0");
}
