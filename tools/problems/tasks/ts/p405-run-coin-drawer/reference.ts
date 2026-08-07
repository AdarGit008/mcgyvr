function readTill(till: number[][]): number[][] {
  if (!Array.isArray(till) || till.length === 0) {
    throw new Error("the till must list at least one denomination");
  }
  const seen = new Set<number>();
  const rows: number[][] = [];
  for (const row of till) {
    if (!Array.isArray(row) || row.length !== 2) {
      throw new Error("each till entry is a denomination and a count");
    }
    const denomination = row[0];
    const count = row[1];
    if (!Number.isInteger(denomination) || denomination < 1) {
      throw new Error("a denomination must be a whole number above nothing");
    }
    if (!Number.isInteger(count) || count < 0) {
      throw new Error("a count must be a whole number of nothing or more");
    }
    if (seen.has(denomination)) {
      throw new Error("denomination " + denomination + " is listed twice");
    }
    seen.add(denomination);
    rows.push([denomination, count]);
  }
  rows.sort((a, b) => b[0] - a[0]);
  return rows;
}

export function runCoinDrawer(
  till: number[][],
  queue: { price: number; paid: number[] }[],
): { till: number[][]; turnedAway: number[]; earnings: number } {
  const rows = readTill(till);
  if (!Array.isArray(queue)) {
    throw new Error("the queue must be a list of purchases");
  }
  let held = new Map<number, number>();
  for (const row of rows) {
    held.set(row[0], row[1]);
  }
  const turnedAway: number[] = [];
  let earnings = 0;
  for (let index = 0; index < queue.length; index++) {
    const purchase = queue[index];
    if (typeof purchase !== "object" || purchase === null || Array.isArray(purchase)) {
      throw new Error("a purchase must be a record");
    }
    const price = purchase.price;
    if (!Number.isInteger(price) || price < 1) {
      throw new Error("a price must be a whole number above nothing");
    }
    const paid = purchase.paid;
    if (!Array.isArray(paid)) {
      throw new Error("the pushed coins must be a list");
    }
    let pushed = 0;
    for (const coin of paid) {
      if (!Number.isInteger(coin) || !held.has(coin)) {
        throw new Error("the till does not handle a coin of " + coin);
      }
      pushed += coin;
    }
    const before = new Map(held);
    for (const coin of paid) {
      held.set(coin, held.get(coin) + 1);
    }
    let owed = pushed - price;
    const handOut = new Map<number, number>();
    if (owed >= 0) {
      for (const row of rows) {
        const denomination = row[0];
        const take = Math.min(held.get(denomination), Math.floor(owed / denomination));
        if (take > 0) {
          handOut.set(denomination, take);
          owed -= take * denomination;
        }
      }
    }
    if (owed !== 0) {
      held = before;
      turnedAway.push(index);
      continue;
    }
    for (const entry of handOut) {
      held.set(entry[0], held.get(entry[0]) - entry[1]);
    }
    earnings += price;
  }
  return {
    till: rows.map((row) => [row[0], held.get(row[0])]),
    turnedAway,
    earnings,
  };
}
