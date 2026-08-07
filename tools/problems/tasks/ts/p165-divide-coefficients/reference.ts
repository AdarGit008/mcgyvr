function checkRun(run: number[]): void {
  if (!Array.isArray(run)) {
    throw new Error("an ascending run must be a list");
  }
  for (const coefficient of run) {
    if (typeof coefficient !== "number" || !Number.isInteger(coefficient)) {
      throw new Error("every coefficient must be a whole number");
    }
  }
  if (run.length > 0 && run[run.length - 1] === 0) {
    throw new Error("an ascending run never ends in a zero");
  }
}

function trim(run: number[]): number[] {
  const out = [...run];
  while (out.length > 0 && out[out.length - 1] === 0) {
    out.pop();
  }
  return out;
}

export function divideCoefficients(
  dividend: number[],
  divisor: number[],
): number[][] {
  checkRun(dividend);
  checkRun(divisor);
  if (divisor.length === 0) {
    throw new Error("the divisor may not be the empty run");
  }
  let rest = [...dividend];
  const span = dividend.length - divisor.length + 1;
  const quotient: number[] = span > 0 ? new Array(span).fill(0) : [];
  const lead = divisor[divisor.length - 1];
  while (rest.length >= divisor.length && rest.length > 0) {
    const shift = rest.length - divisor.length;
    const top = rest[rest.length - 1];
    if (top % lead !== 0) {
      throw new Error("the division leaves the whole numbers");
    }
    const factor = top / lead;
    quotient[shift] = factor;
    for (let i = 0; i < divisor.length; i++) {
      rest[shift + i] -= factor * divisor[i];
    }
    rest = trim(rest);
  }
  return [trim(quotient), rest];
}
