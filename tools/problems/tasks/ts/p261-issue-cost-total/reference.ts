export function issueCostTotal(moves: Array<Record<string, unknown>>): number {
  if (!Array.isArray(moves)) {
    throw new Error("issueCostTotal expects a list of movements");
  }
  const bin: Array<[number, number]> = [];
  let onHand = 0;
  let charged = 0;
  for (const move of moves) {
    if (move === null || typeof move !== "object" || Array.isArray(move)) {
      throw new Error("every movement is a record");
    }
    const kind = move.kind;
    if (kind !== "in" && kind !== "out") {
      throw new Error(`unknown movement kind ${String(kind)}`);
    }
    const units = move.units;
    if (!Number.isInteger(units) || (units as number) <= 0) {
      throw new Error("units must be a whole number above zero");
    }
    const count = units as number;
    if (kind === "in") {
      const cents = move.cents;
      if (!Number.isInteger(cents) || (cents as number) < 0) {
        throw new Error("an arrival is priced in whole cents, not below zero");
      }
      bin.push([count, cents as number]);
      onHand += count;
      continue;
    }
    if ("cents" in move) {
      throw new Error("an issue carries no price of its own");
    }
    if (count > onHand) {
      throw new Error("the bin does not hold that many parts");
    }
    let wanted = count;
    while (wanted > 0) {
      const consignment = bin[0];
      const taken = Math.min(wanted, consignment[0]);
      charged += taken * consignment[1];
      consignment[0] -= taken;
      wanted -= taken;
      onHand -= taken;
      if (consignment[0] === 0) {
        bin.shift();
      }
    }
  }
  return charged;
}
