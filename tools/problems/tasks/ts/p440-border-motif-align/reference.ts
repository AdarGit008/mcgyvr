function isCount(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value) && value >= 1;
}

export function alignBorderMotifs(
  widths: number[],
  patternLength: number,
): { edges: number[]; freshAt: number } {
  if (!Array.isArray(widths)) {
    throw new Error("the widths are a list");
  }
  if (widths.length === 0) {
    throw new Error("the wall carries no strips");
  }
  if (!isCount(patternLength)) {
    throw new Error("the pattern length is a whole number of one or more");
  }

  const edges: number[] = [];
  let running = 0;
  for (const width of widths) {
    if (!isCount(width)) {
      throw new Error("a strip width is a whole number of one or more");
    }
    edges.push(running % patternLength);
    running += width;
  }

  let freshAt = 0;
  for (let i = 1; i < edges.length; i++) {
    if (edges[i] === 0) {
      freshAt = i + 1;
      break;
    }
  }
  return { edges, freshAt };
}
