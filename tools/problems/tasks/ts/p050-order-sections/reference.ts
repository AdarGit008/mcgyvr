export function orderSections(labels: string[]): string[] {
  if (!Array.isArray(labels)) {
    throw new Error("labels must be a list");
  }
  const seen = new Set<string>();
  const parsed: [string, number[]][] = [];
  for (const label of labels) {
    if (typeof label !== "string" || !/^(?:0|[1-9]\d*)(?:\.(?:0|[1-9]\d*))*$/.test(label)) {
      throw new Error("malformed section label");
    }
    if (seen.has(label)) {
      throw new Error("duplicate section label");
    }
    seen.add(label);
    parsed.push([label, label.split(".").map(Number)]);
  }
  parsed.sort((a, b) => {
    const [, x] = a;
    const [, y] = b;
    const n = Math.min(x.length, y.length);
    for (let i = 0; i < n; i++) {
      if (x[i] !== y[i]) {
        return x[i] - y[i];
      }
    }
    return x.length - y.length;
  });
  return parsed.map(([label]) => label);
}
