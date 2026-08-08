export function settleLedger(
  entries: Array<Record<string, unknown>>,
): Array<[string, number]> {
  if (!Array.isArray(entries)) {
    throw new Error("settleLedger expects a list of entries");
  }
  const seen = new Set<number>();
  for (const entry of entries) {
    if (
      typeof entry !== "object" ||
      entry === null ||
      !("account" in entry) ||
      !("amount" in entry) ||
      !("seq" in entry)
    ) {
      throw new Error("entry is missing a required property");
    }
    const { account, amount, seq } = entry as {
      account: unknown;
      amount: unknown;
      seq: unknown;
    };
    if (typeof account !== "string" || account === "") {
      throw new Error("account must be a non-empty string");
    }
    if (!Number.isInteger(amount)) {
      throw new Error("amount must be an integer");
    }
    if (!Number.isInteger(seq)) {
      throw new Error("seq must be an integer");
    }
    if (seen.has(seq as number)) {
      throw new Error(`duplicate seq ${seq}`);
    }
    seen.add(seq as number);
  }
  const ordered = [...entries].sort(
    (a, b) => (a.seq as number) - (b.seq as number),
  );
  const balances = new Map<string, number>();
  for (const entry of ordered) {
    const account = entry.account as string;
    const next = (balances.get(account) ?? 0) + (entry.amount as number);
    if (next < 0) {
      throw new Error(`balance of ${account} falls below zero at seq ${entry.seq}`);
    }
    balances.set(account, next);
  }
  return [...balances.entries()]
    .filter(([, balance]) => balance !== 0)
    .sort((a, b) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0));
}
