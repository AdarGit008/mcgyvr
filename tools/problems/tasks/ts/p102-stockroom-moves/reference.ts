export function processStockMoves(
  moves: Array<Record<string, unknown>>,
): { levels: Record<string, number>; refused: Array<[number, string]> } {
  const levels: Record<string, number> = {};
  const refused: Array<[number, string]> = [];
  moves.forEach((move, index) => {
    const op = move.op;
    const item = move.item;
    const qty = move.qty;
    if (op !== "receive" && op !== "issue" && op !== "recount") {
      throw new Error(`unknown op at move ${index}`);
    }
    if (typeof item !== "string" || item.length === 0) {
      throw new Error(`bad item at move ${index}`);
    }
    if (typeof qty !== "number" || !Number.isInteger(qty)) {
      throw new Error(`qty must be an integer at move ${index}`);
    }
    if ((op === "receive" || op === "issue") && qty < 1) {
      throw new Error(`qty below 1 at move ${index}`);
    }
    if (op === "recount" && qty < 0) {
      throw new Error(`recount below 0 at move ${index}`);
    }
    if (op === "receive") {
      levels[item] = (levels[item] ?? 0) + qty;
    } else if (op === "recount") {
      levels[item] = qty;
    } else if (!(item in levels)) {
      refused.push([index, "unknown_item"]);
    } else if (levels[item] < qty) {
      refused.push([index, "short"]);
    } else {
      levels[item] -= qty;
    }
  });
  return { levels, refused };
}
