/** One warehouse item's stockbook under moving-average costing. */

export function receiptCents(qty: number, unitCents: number): number {
  if (!Number.isInteger(qty) || qty <= 0) {
    throw new Error("receive quantity must be a positive integer");
  }
  if (!Number.isInteger(unitCents) || unitCents < 0) {
    throw new Error("unit cost must be a non-negative integer of cents");
  }
  return qty * unitCents;
}

export function runStockbook(moves: (string | number)[][]): { held: number; worth: number; issued: number } {
  let held = 0;
  let worth = 0;
  let issued = 0;
  for (const move of moves) {
    if (move[0] === "receive") {
      const qty = move[1] as number;
      worth += receiptCents(qty, move[2] as number);
      held += qty;
    } else if (move[0] === "issue") {
      const qty = move[1] as number;
      if (!Number.isInteger(qty) || qty <= 0) {
        throw new Error("issue quantity must be a positive integer");
      }
      if (qty > held) {
        throw new Error("issue exceeds the stock held");
      }
      const relief = Math.floor((worth * qty) / held);
      worth -= relief;
      issued += relief;
      held -= qty;
    }
  }
  return { held, worth, issued };
}
