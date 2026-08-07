function readHopper(hopper: number[][]): number[][] {
  if (!Array.isArray(hopper) || hopper.length === 0) {
    throw new Error("the hopper must list at least one face");
  }
  const seen = new Set<number>();
  const faces: number[][] = [];
  for (const row of hopper) {
    if (!Array.isArray(row) || row.length !== 2) {
      throw new Error("each hopper entry is a face and a stock");
    }
    const face = row[0];
    const stock = row[1];
    if (!Number.isInteger(face) || face < 1) {
      throw new Error("a face value must be a whole number above nothing");
    }
    if (!Number.isInteger(stock) || stock < 0) {
      throw new Error("a stock must be a whole number of nothing or more");
    }
    if (seen.has(face)) {
      throw new Error("face " + face + " is listed twice");
    }
    seen.add(face);
    faces.push([face, stock]);
  }
  faces.sort((a, b) => b[0] - a[0]);
  return faces;
}

export function dispenseExactChange(amount: number, hopper: number[][]): number[][] {
  if (!Number.isInteger(amount) || amount < 0 || amount > 100000) {
    throw new Error("the amount must be a whole number of 0 through 100000");
  }
  const faces = readHopper(hopper);
  const unreachable = amount + 1;
  let deeper: number[] = new Array(amount + 1).fill(unreachable);
  deeper[0] = 0;
  const taken: number[][] = new Array(faces.length);
  for (let index = faces.length - 1; index >= 0; index--) {
    const face = faces[index][0];
    const stock = faces[index][1];
    const level = new Array(amount + 1).fill(unreachable);
    const picks = new Array(amount + 1).fill(0);
    for (let rest = 0; rest <= amount; rest++) {
      let fewest = unreachable;
      let best = 0;
      const limit = Math.min(stock, Math.floor(rest / face));
      for (let count = 0; count <= limit; count++) {
        const below = deeper[rest - count * face];
        if (below === unreachable) {
          continue;
        }
        const coins = below + count;
        if (coins < fewest || (coins === fewest && count > best)) {
          fewest = coins;
          best = count;
        }
      }
      level[rest] = fewest;
      picks[rest] = best;
    }
    taken[index] = picks;
    deeper = level;
  }
  if (deeper[amount] === unreachable) {
    throw new Error("the hopper cannot pay " + amount + " exactly");
  }
  const payout: number[][] = [];
  let rest = amount;
  for (let index = 0; index < faces.length; index++) {
    const count = taken[index][rest];
    if (count > 0) {
      payout.push([faces[index][0], count]);
    }
    rest -= count * faces[index][0];
  }
  return payout;
}
