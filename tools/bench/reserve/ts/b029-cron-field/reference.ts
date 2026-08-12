/** Expand one cron schedule field into the values it matches. */

function parsePart(text: string, what: string): number {
  if (!/^[0-9]+$/.test(text)) {
    throw new Error(what + " must be digits");
  }
  return Number(text);
}

export function expandCronField(field: string, low: number, high: number): number[] {
  if (typeof field !== "string") {
    throw new Error("expandCronField expects a string field");
  }
  if (field === "") {
    throw new Error("empty field");
  }
  const matched = new Set<number>();
  for (const item of field.split(",")) {
    if (item === "") {
      throw new Error("empty item");
    }
    const pieces = item.split("/");
    if (pieces.length > 2) {
      throw new Error("more than one step");
    }
    const core = pieces[0];
    let step = 1;
    if (pieces.length === 2) {
      step = parsePart(pieces[1], "step");
      if (step === 0) {
        throw new Error("step of zero");
      }
    }
    let start: number;
    let end: number;
    if (core === "*") {
      start = low;
      end = high;
    } else if (core.includes("-")) {
      const ends = core.split("-");
      if (ends.length !== 2) {
        throw new Error("malformed range");
      }
      start = parsePart(ends[0], "range low");
      end = parsePart(ends[1], "range high");
      if (start > end) {
        throw new Error("range low exceeds range high");
      }
    } else {
      if (pieces.length === 2) {
        throw new Error("step attached to a single number");
      }
      start = parsePart(core, "number");
      end = start;
    }
    if (core !== "*" && (start < low || end > high)) {
      throw new Error("number outside the bounds");
    }
    for (let value = start; value <= end; value += step) {
      matched.add(value);
    }
  }
  return [...matched].sort((a, b) => a - b);
}
