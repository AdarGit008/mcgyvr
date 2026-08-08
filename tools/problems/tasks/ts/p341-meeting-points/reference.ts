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

function checkStart(value: number): void {
  if (!Number.isInteger(value) || value < 0 || value > 1000000) {
    throw new Error("a start must be a whole number from 0 through 1000000");
  }
}

function checkStride(value: number): void {
  if (!Number.isInteger(value) || value < 1 || value > 100000) {
    throw new Error("a stride must be a whole number from 1 through 100000");
  }
}

export function meetingPoints(
  startA: number,
  strideA: number,
  startB: number,
  strideB: number,
  count: number,
): number[] {
  checkStart(startA);
  checkStart(startB);
  checkStride(strideA);
  checkStride(strideB);
  if (!Number.isInteger(count) || count < 0 || count > 20) {
    throw new Error("count must be a whole number from 0 through 20");
  }

  const common = greatestCommon(strideA, strideB);
  if (floorMod(startB - startA, common) !== 0) {
    return [];
  }
  const stride = (strideA / common) * strideB;
  const reduced = strideB / common;
  const shift = floorMod((startB - startA) / common, reduced);
  const step = (shift * inverse(strideA / common, reduced)) % reduced;
  let landing = floorMod(startA + strideA * step, stride);

  const threshold = Math.max(startA, startB);
  if (landing < threshold) {
    const gap = threshold - landing;
    let jumps = Math.trunc(gap / stride);
    while (jumps * stride < gap) {
      jumps += 1;
    }
    while (jumps > 0 && (jumps - 1) * stride >= gap) {
      jumps -= 1;
    }
    landing += jumps * stride;
  }

  const landings: number[] = [];
  for (let index = 0; index < count; index++) {
    landings.push(landing + index * stride);
  }
  return landings;
}
