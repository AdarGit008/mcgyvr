export function mergeMarkup(
  spans: Array<{ start: number; end: number; tag: string }>,
): Array<[number, number, string]> {
  const byTag: Record<string, Array<[number, number]>> = {};
  for (const span of spans) {
    const { start, end, tag } = span;
    if (!Number.isInteger(start) || !Number.isInteger(end)) {
      throw new Error("span bounds must be integers");
    }
    if (start < 0 || start >= end) {
      throw new Error("bad span bounds");
    }
    if (typeof tag !== "string" || tag.length === 0) {
      throw new Error("bad tag");
    }
    (byTag[tag] ??= []).push([start, end]);
  }
  const merged: Array<[number, number, string]> = [];
  for (const tag of Object.keys(byTag)) {
    const list = byTag[tag].sort((a, b) => a[0] - b[0]);
    let [lo, hi] = list[0];
    for (let i = 1; i < list.length; i++) {
      const [s, e] = list[i];
      if (s <= hi) {
        hi = Math.max(hi, e);
      } else {
        merged.push([lo, hi, tag]);
        lo = s;
        hi = e;
      }
    }
    merged.push([lo, hi, tag]);
  }
  merged.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  for (let i = 1; i < merged.length; i++) {
    if (merged[i][0] < merged[i - 1][1]) {
      throw new Error("spans with different tags share a position");
    }
  }
  return merged;
}
