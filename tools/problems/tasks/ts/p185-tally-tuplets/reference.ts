const WHOLE = 64;
const DENOMINATORS = [1, 2, 4, 8, 16, 32, 64];

function spanUnits(text: string): number {
  const shape = /^(\d+)\/(\d+)$/.exec(text);
  if (shape === null) {
    throw new Error("not a plain span: " + text);
  }
  const [, top, bottom] = shape;
  if (top.length > 1 && top[0] === "0") {
    throw new Error("numerator written with a padding zero");
  }
  if (Number(top) === 0) {
    throw new Error("numerator of zero");
  }
  const denominator = Number(bottom);
  if (bottom.length > 1 && bottom[0] === "0") {
    throw new Error("denominator written with a padding zero");
  }
  if (!DENOMINATORS.includes(denominator)) {
    throw new Error("denominator outside the seven allowed");
  }
  return Number(top) * (WHOLE / denominator);
}

function entryUnits(entry: string): number {
  const brace = entry.indexOf("{");
  if (brace === -1) {
    if (entry.includes("}")) {
      throw new Error("closing brace with nothing open");
    }
    return spanUnits(entry);
  }
  const figure = entry.slice(0, brace);
  if (!/^\d+$/.test(figure) || (figure.length > 1 && figure[0] === "0")) {
    throw new Error("bad repetition figure");
  }
  if (Number(figure) < 2) {
    throw new Error("figure below two");
  }
  if (!entry.endsWith("}") || entry.length === brace + 1) {
    throw new Error("brace never closed");
  }
  const body = entry.slice(brace + 1, entry.length - 1);
  if (body === "") {
    throw new Error("brace closed with nothing inside");
  }
  let total = 0;
  for (const member of body.split("+")) {
    total += spanUnits(member);
  }
  const stretched = total * (Number(figure) - 1);
  if (stretched % Number(figure) !== 0) {
    throw new Error("squeeze is not a whole number of units");
  }
  return stretched / Number(figure);
}

export function tallyTuplets(score: string, meter: string): number[] {
  if (typeof score !== "string" || typeof meter !== "string") {
    throw new Error("score and meter must be strings");
  }
  const holds = spanUnits(meter);
  const report: number[] = [];
  for (const measure of score.split(";")) {
    const entries = measure.split(" ").filter((piece) => piece.length > 0);
    if (entries.length === 0) {
      throw new Error("a measure with no entries in it");
    }
    let carried = 0;
    for (const entry of entries) {
      carried += entryUnits(entry);
    }
    report.push(carried - holds);
  }
  return report;
}
