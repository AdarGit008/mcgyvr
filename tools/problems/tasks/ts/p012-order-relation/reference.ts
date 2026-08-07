export function orderRelation(
  pairs: [string, string][],
  x: string,
  y: string,
): string {
  if (x === y) {
    throw new Error("query items must differ");
  }
  const next = new Map<string, string[]>();
  const known = new Set<string>();
  for (const [a, b] of pairs) {
    known.add(a);
    known.add(b);
    const outs = next.get(a) ?? [];
    outs.push(b);
    next.set(a, outs);
  }
  if (!known.has(x) || !known.has(y)) {
    throw new Error("query items must appear in some pair");
  }
  const reaches = (from: string, to: string): boolean => {
    const seen = new Set<string>([from]);
    const stack: string[] = [from];
    while (stack.length > 0) {
      const node = stack.pop() as string;
      for (const out of next.get(node) ?? []) {
        if (out === to) {
          return true;
        }
        if (!seen.has(out)) {
          seen.add(out);
          stack.push(out);
        }
      }
    }
    return false;
  };
  const forward = reaches(x, y);
  const backward = reaches(y, x);
  if (forward && backward) {
    return "both";
  }
  if (forward) {
    return "before";
  }
  if (backward) {
    return "after";
  }
  return "unordered";
}
