/** Evaluate a mass tally written with unit-suffixed terms. */

const GRAMS: Record<string, number> = {
  g: 1,
  kg: 1000,
  t: 1000000,
};

function termGrams(token: string): number {
  const match = /^(0|[1-9][0-9]*)(g|kg|t)$/.exec(token);
  if (match === null) {
    throw new Error("a term is a whole count directly on its unit");
  }
  return Number(match[1]) * GRAMS[match[2]];
}

export function massExpression(text: string, unit: string): number {
  if (typeof text !== "string" || text === "") {
    throw new Error("the tally must be a non-empty string");
  }
  if (!(unit in GRAMS)) {
    throw new Error("the goal unit must be g, kg or t");
  }
  const tokens = text.split(" ");
  if (tokens.length % 2 === 0) {
    throw new Error("terms and operators must alternate, ending on a term");
  }
  let grams = termGrams(tokens[0]);
  for (let i = 1; i < tokens.length; i += 2) {
    const op = tokens[i];
    const value = termGrams(tokens[i + 1]);
    if (op === "+") {
      grams += value;
    } else if (op === "-") {
      grams -= value;
    } else {
      throw new Error("operators are + and -");
    }
    if (grams < 0) {
      throw new Error("the tally must never dip below zero");
    }
  }
  if (grams % GRAMS[unit] !== 0) {
    throw new Error("the total must come out whole in the goal unit");
  }
  return grams / GRAMS[unit];
}
