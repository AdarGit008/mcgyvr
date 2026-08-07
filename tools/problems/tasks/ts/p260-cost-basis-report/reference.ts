export function costBasisReport(events: unknown[][]): {
  fifoSold: number;
  averageSold: number;
  unitsLeft: number;
  fifoValue: number;
  averageValue: number;
} {
  if (!Array.isArray(events)) {
    throw new Error("costBasisReport expects a list of warehouse events");
  }
  const layers: Array<[number, number]> = [];
  let fifoSold = 0;
  let poolUnits = 0;
  let poolCost = 0;
  let averageSold = 0;

  for (const row of events) {
    if (!Array.isArray(row) || row.length === 0) {
      throw new Error("every event is a row naming buy or sell");
    }
    const kind = row[0];
    if (kind !== "buy" && kind !== "sell") {
      throw new Error(`unknown event ${String(kind)}`);
    }
    const units = row[1];
    if (!Number.isInteger(units) || (units as number) <= 0) {
      throw new Error("units must be a whole number above zero");
    }
    const count = units as number;
    if (kind === "buy") {
      if (row.length !== 3) {
        throw new Error("a receipt is a kind, a unit count and a unit price");
      }
      const price = row[2];
      if (!Number.isInteger(price) || (price as number) < 0) {
        throw new Error("a unit price must be a whole number of cents, not below zero");
      }
      layers.push([count, price as number]);
      poolUnits += count;
      poolCost += count * (price as number);
      continue;
    }
    if (row.length !== 2) {
      throw new Error("a despatch is a kind and a unit count");
    }
    if (count > poolUnits) {
      throw new Error("a despatch cannot exceed the stock on hand");
    }
    let wanted = count;
    while (wanted > 0) {
      const layer = layers[0];
      const taken = Math.min(wanted, layer[0]);
      fifoSold += taken * layer[1];
      layer[0] -= taken;
      wanted -= taken;
      if (layer[0] === 0) {
        layers.shift();
      }
    }
    const charged = Math.floor((poolCost * count) / poolUnits);
    averageSold += charged;
    poolCost -= charged;
    poolUnits -= count;
  }

  let fifoValue = 0;
  for (const [units, price] of layers) {
    fifoValue += units * price;
  }
  return {
    fifoSold,
    averageSold,
    unitsLeft: poolUnits,
    fifoValue,
    averageValue: poolCost,
  };
}
