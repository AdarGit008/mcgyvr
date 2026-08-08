export function replayEnvelopes(
  envelopes: Array<{ name: string; monthly: number; cap: number }>,
  months: Array<Array<[string, number]>>,
): { balances: Array<[string, number]>; forfeited: number } {
  const order: string[] = [];
  const monthlyOf = new Map<string, number>();
  const capOf = new Map<string, number>();
  const balance = new Map<string, number>();
  for (const envelope of envelopes) {
    const { name, monthly, cap } = envelope;
    if (typeof name !== "string" || name === "") {
      throw new Error("an envelope name must be a non-empty string");
    }
    if (monthlyOf.has(name)) {
      throw new Error("duplicate envelope name");
    }
    if (!Number.isInteger(monthly) || monthly < 0) {
      throw new Error("monthly must be a non-negative integer");
    }
    if (!Number.isInteger(cap) || cap < 0) {
      throw new Error("cap must be a non-negative integer");
    }
    order.push(name);
    monthlyOf.set(name, monthly);
    capOf.set(name, cap);
    balance.set(name, 0);
  }
  let forfeited = 0;
  for (const month of months) {
    for (const name of order) {
      balance.set(name, (balance.get(name) as number) + (monthlyOf.get(name) as number));
    }
    for (const outlay of month) {
      const [name, amount] = outlay;
      if (!balance.has(name)) {
        throw new Error("outlay names an unknown envelope");
      }
      if (!Number.isInteger(amount) || amount < 1) {
        throw new Error("an outlay amount must be a positive integer");
      }
      balance.set(name, (balance.get(name) as number) - amount);
    }
    for (const name of order) {
      const held = balance.get(name) as number;
      const cap = capOf.get(name) as number;
      if (held > cap) {
        forfeited += held - cap;
        balance.set(name, cap);
      }
    }
  }
  return {
    balances: order.map((name) => [name, balance.get(name) as number]),
    forfeited,
  };
}
