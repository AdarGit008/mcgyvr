/** Plan courier loads by halving a consignment until every load fits. */
export function planBatches(
  units: number,
  capacity: number,
): { loads: number[]; splits: number; rounds: number } {
  if (!Number.isInteger(units) || units <= 0) {
    throw new Error("units must be a positive integer");
  }
  if (!Number.isInteger(capacity) || capacity <= 0) {
    throw new Error("capacity must be a positive integer");
  }
  if (units <= capacity) {
    return { loads: [units], splits: 0, rounds: 0 };
  }
  const upper = Math.ceil(units / 2);
  const first = planBatches(upper, capacity);
  const second = planBatches(units - upper, capacity);
  return {
    loads: [...first.loads, ...second.loads],
    splits: 1 + first.splits + second.splits,
    rounds: 1 + Math.max(first.rounds, second.rounds),
  };
}
