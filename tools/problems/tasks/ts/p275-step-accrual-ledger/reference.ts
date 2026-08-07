export function stepAccrualLedger(opening: number, steps: number[][]): number[][] {
  if (!Number.isInteger(opening) || opening < 0) {
    throw new Error("the opening balance must be a whole number of cents, not below zero");
  }
  if (!Array.isArray(steps) || steps.length === 0) {
    throw new Error("the schedule must be a non-empty list of steps");
  }

  const divisor = 10000 * 365;
  const rows: number[][] = [];
  let principal = opening;
  let heap = 0;
  let leftover = 0;

  for (const step of steps) {
    if (!Array.isArray(step) || step.length !== 3) {
      throw new Error("a step is three values long");
    }
    const [dayCount, tenThousandths, capitalise] = step;
    for (const value of step) {
      if (!Number.isInteger(value)) {
        throw new Error("every value in a step is a whole number");
      }
    }
    if (dayCount < 1) {
      throw new Error("a step spans at least one day");
    }
    if (tenThousandths < 0) {
      throw new Error("a rate must not be below zero");
    }
    if (capitalise !== 0 && capitalise !== 1) {
      throw new Error("capitalise is 0 or 1");
    }

    const pot = principal * tenThousandths * dayCount + leftover;
    const earned = Math.floor(pot / divisor);
    leftover = pot - earned * divisor;
    if (capitalise === 1) {
      principal += earned;
    } else {
      heap += earned;
    }
    rows.push([earned, principal, heap]);
  }
  return rows;
}
