export function selectorHits(values: number[], selector: string): number {
  if (!Array.isArray(values) || values.some((v) => !Number.isInteger(v))) {
    throw new Error("values must be a list of integers");
  }
  if (typeof selector !== "string" || selector === "") {
    throw new Error("selector must be a non-empty string");
  }
  const spans: number[][] = [];
  for (const term of selector.split(",")) {
    const match = /^(\d+)(?:-(\d+))?$/.exec(term);
    if (match === null) {
      throw new Error("malformed selector term: " + term);
    }
    const low = Number(match[1]);
    const high = match[2] === undefined ? low : Number(match[2]);
    if (low > high) {
      throw new Error("range low end exceeds its high end: " + term);
    }
    spans.push([low, high]);
  }
  return values.filter((v) => spans.some(([low, high]) => low <= v && v <= high)).length;
}
