export function traceUnevenPayoff(
  opening: number,
  rate: number,
  instalments: unknown,
): number[][] {
  if (!Number.isInteger(opening) || !Number.isInteger(rate)) {
    throw new Error("opening and rate must be whole numbers");
  }
  if (opening <= 0) {
    throw new Error("opening must be above zero");
  }
  if (rate < 0) {
    throw new Error("rate must not fall below zero");
  }
  if (!Array.isArray(instalments) || instalments.length === 0) {
    throw new Error("instalments must be a non-empty list");
  }
  for (const paid of instalments) {
    if (!Number.isInteger(paid) || paid < 0) {
      throw new Error("every instalment must be a whole number of cents, not below zero");
    }
  }

  const rows: number[][] = [];
  let principal = opening;
  let pile = 0;
  for (const paid of instalments as number[]) {
    const levy = Math.floor((principal * rate + 5000) / 10000);
    if (paid > pile + levy + principal) {
      throw new Error("an instalment may not exceed everything then owed");
    }
    let left = paid;
    const toPile = left < pile ? left : pile;
    pile -= toPile;
    left -= toPile;
    const toLevy = left < levy ? left : levy;
    left -= toLevy;
    pile += levy - toLevy;
    const toPrincipal = left;
    principal -= toPrincipal;
    rows.push([paid, levy, toPile + toLevy, toPrincipal, principal, pile]);
  }
  if (principal > 0 || pile > 0) {
    rows.push([pile + principal, 0, pile, principal, 0, 0]);
  }
  return rows;
}
