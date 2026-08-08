const SIZE_LIMIT = 1000000000;

export function foldFractionTerms(
  numerator: number,
  denominator: number,
): number[] {
  if (!Number.isInteger(numerator) || Math.abs(numerator) > SIZE_LIMIT) {
    throw new Error("the numerator must be a whole number within the limit");
  }
  if (
    !Number.isInteger(denominator) ||
    denominator < 1 ||
    denominator > SIZE_LIMIT
  ) {
    throw new Error("the denominator must be a whole number from 1 up");
  }

  const run: number[] = [];
  let top = numerator;
  let bottom = denominator;
  while (bottom !== 0) {
    let whole = Math.trunc(top / bottom);
    let rest = top - whole * bottom;
    while (rest < 0) {
      whole -= 1;
      rest += bottom;
    }
    while (rest >= bottom) {
      whole += 1;
      rest -= bottom;
    }
    run.push(whole + 0);
    top = bottom;
    bottom = rest;
  }
  return run;
}
