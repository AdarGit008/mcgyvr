/** Print-dialog page selections, "1-3,7" style, expanded to page lists. */
export function readSpan(segment: string): number[] {
  const m = /^([1-9]\d*)(?:-([1-9]\d*))?$/.exec(segment);
  if (m === null) {
    throw new Error("malformed piece: " + segment);
  }
  const low = Number(m[1]);
  const high = m[2] === undefined ? low : Number(m[2]);
  if (high < low) {
    throw new Error("span runs backwards: " + segment);
  }
  return [low, high];
}

export function expandSelection(spec: string): number[] {
  if (typeof spec !== "string" || spec.length === 0) {
    throw new Error("expandSelection expects a non-empty string");
  }
  const pages: number[] = [];
  for (const piece of spec.split(",")) {
    const [low, high] = readSpan(piece);
    if (pages.length > 0 && low <= pages[pages.length - 1]) {
      throw new Error("selection must move forward: " + piece);
    }
    for (let page = low; page <= high; page++) {
      pages.push(page);
    }
  }
  return pages;
}
