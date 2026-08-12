export function shelfCount(
  onHand: number,
  moves: [string, number][],
): { ending: number; peak: number } {
  if (!Number.isInteger(onHand) || onHand < 0) {
    throw new Error("starting count must be a non-negative integer");
  }
  let ending = onHand;
  let peak = onHand;
  for (const move of moves) {
    if (!Array.isArray(move) || move.length !== 2) {
      throw new Error("each move is a [kind, qty] pair");
    }
    const [kind, qty] = move;
    if (!Number.isInteger(qty) || qty <= 0) {
      throw new Error("qty must be a positive integer");
    }
    if (kind === "receive") {
      ending += qty;
      if (ending > peak) peak = ending;
    } else if (kind === "issue") {
      if (qty > ending) throw new Error("issue exceeds the count on the shelf");
      ending -= qty;
    } else {
      throw new Error("unknown move kind: " + kind);
    }
  }
  return { ending, peak };
}
