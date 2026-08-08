function whole(value: unknown, least: number, what: string): number {
  if (typeof value !== "number" || !Number.isInteger(value) || value < least) {
    throw new Error(`${what} must be a whole number of at least ${least}`);
  }
  return value;
}

/** What each handful of dice is worth once the weakest are set aside. */
export function resolveDicePool(
  pools: Record<string, number>[],
  rolls: number[],
): Record<string, unknown> {
  if (!Array.isArray(pools) || pools.length === 0) {
    throw new Error("there must be at least one pool");
  }
  if (!Array.isArray(rolls)) {
    throw new Error("the rolls must be a list");
  }

  const totals: number[] = [];
  const dropped: number[][] = [];
  let at = 0;

  for (const pool of pools) {
    const sides = whole(pool.sides, 2, "sides");
    const dice = whole(pool.dice, 1, "dice");
    const keep = whole(pool.keep, 1, "keep");
    if (keep > dice) {
      throw new Error(`a pool cannot hold ${keep} of ${dice} dice`);
    }

    const base = at;
    const taken: number[] = [];
    for (let die = 0; die < dice; die++) {
      if (at >= rolls.length) {
        throw new Error("the rolls run out");
      }
      const roll = rolls[at];
      at += 1;
      if (!Number.isInteger(roll) || roll < 1 || roll > sides) {
        throw new Error(`${String(roll)} is not a roll of a ${sides}-sided die`);
      }
      taken.push(roll);
    }

    const order = taken.map((_, index) => index);
    order.sort((left, right) => taken[right] - taken[left] || left - right);
    const held = new Set(order.slice(0, keep));

    let total = 0;
    const aside: number[] = [];
    for (let index = 0; index < taken.length; index++) {
      if (held.has(index)) {
        total += taken[index];
      } else {
        aside.push(base + index);
      }
    }
    totals.push(total);
    dropped.push(aside);
  }

  if (at !== rolls.length) {
    throw new Error(`${rolls.length - at} rolls were left undrawn`);
  }
  return { totals, dropped };
}
