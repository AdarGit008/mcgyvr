/** Cheapest way up a tolled scaffold whose tolls arrive as digit strings. */
export function climbBudget(tolls: string[]): number {
  const paid: number[] = [];
  for (let i = 0; i < tolls.length; i++) {
    const written = tolls[i];
    if (typeof written !== "string" || !/^[0-9]+$/.test(written)) {
      throw new Error("rung " + i + " is not written as digits");
    }
    if (written.length > 1 && written[0] === "0") {
      throw new Error("rung " + i + " carries a leading zero");
    }
    paid.push(Number(written));
  }
  // Cheapest totals for standing two rungs back and one rung back.
  let twoBack = 0;
  let oneBack = 0;
  for (const toll of paid) {
    const here = toll + Math.min(twoBack, oneBack);
    twoBack = oneBack;
    oneBack = here;
  }
  return Math.min(twoBack, oneBack);
}
