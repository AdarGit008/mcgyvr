const SPAN_CEILING = 1000000000;

function floorMod(value: number, span: number): number {
  const rest = value % span;
  return rest < 0 ? rest + span : rest;
}

function greatestCommon(a: number, b: number): number {
  let left = Math.abs(a);
  let right = Math.abs(b);
  while (right !== 0) {
    const rest = left % right;
    left = right;
    right = rest;
  }
  return left;
}

function inverse(value: number, span: number): number {
  if (span === 1) {
    return 0;
  }
  let older = span;
  let newer = floorMod(value, span);
  let coefficientOlder = 0;
  let coefficientNewer = 1;
  while (newer !== 0) {
    const quotient = Math.floor(older / newer);
    const restNext = older - quotient * newer;
    older = newer;
    newer = restNext;
    const coefficientNext = coefficientOlder - quotient * coefficientNewer;
    coefficientOlder = coefficientNewer;
    coefficientNewer = coefficientNext;
  }
  return floorMod(coefficientOlder, span);
}

export function blendCongruences(pairs: number[][]): number[] {
  if (!Array.isArray(pairs)) {
    throw new Error("pairs must be a list");
  }
  if (pairs.length === 0) {
    throw new Error("there is nothing to merge");
  }

  let rest = 0;
  let span = 1;
  for (const pair of pairs) {
    if (!Array.isArray(pair) || pair.length !== 2) {
      throw new Error("every entry must be a pair");
    }
    const incoming = pair[0];
    const width = pair[1];
    if (!Number.isInteger(width) || width < 1 || width > 1000000) {
      throw new Error("a span must be a whole number from 1 through 1000000");
    }
    if (!Number.isInteger(incoming) || Math.abs(incoming) > SPAN_CEILING) {
      throw new Error("a rest must be a whole number within the limit");
    }

    const want = floorMod(incoming, width);
    const common = greatestCommon(span, width);
    if (floorMod(want - rest, common) !== 0) {
      return [];
    }
    const merged = (span / common) * width;
    if (merged > SPAN_CEILING) {
      throw new Error("the merged span swells past the limit");
    }
    const reduced = width / common;
    const shift = floorMod((want - rest) / common, reduced);
    const step = (shift * inverse(span / common, reduced)) % reduced;
    rest = floorMod(rest + span * step, merged);
    span = merged;
  }
  return [rest, span];
}
