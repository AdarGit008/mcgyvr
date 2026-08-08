export function smoothWithTaps(samples: number[], taps: number[]): number[] {
  if (!Array.isArray(samples) || samples.length === 0) {
    throw new Error("the series must be a non-empty list");
  }
  for (const sample of samples) {
    if (typeof sample !== "number" || !Number.isInteger(sample)) {
      throw new Error("every sample is a whole number");
    }
  }
  if (!Array.isArray(taps) || taps.length === 0) {
    throw new Error("the weights must be a non-empty list");
  }
  for (const weight of taps) {
    if (typeof weight !== "number" || !Number.isInteger(weight)) {
      throw new Error("every weight is a whole number");
    }
  }
  if (taps.length % 2 === 0) {
    throw new Error("the weights must come to an odd count");
  }

  const span = samples.length;
  const middle = (taps.length - 1) / 2;
  const period = span > 1 ? 2 * span - 2 : 1;
  const hinge = (index: number): number => {
    if (span === 1) return 0;
    let folded = ((index % period) + period) % period;
    if (folded >= span) {
      folded = period - folded;
    }
    return folded;
  };

  const answer: number[] = [];
  for (let at = 0; at < span; at++) {
    let total = 0;
    for (let tap = 0; tap < taps.length; tap++) {
      total += samples[hinge(at + tap - middle)] * taps[tap];
    }
    answer.push(total);
  }
  return answer;
}
