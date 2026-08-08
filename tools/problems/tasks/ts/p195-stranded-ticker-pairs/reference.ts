export function strandedTickerPairs(legs: unknown[][]): string[] {
  if (!Array.isArray(legs) || legs.length === 0) {
    throw new Error("the desk published no legs");
  }
  const forward = new Map<string, string[]>();
  const published = new Set<string>();
  const tickers = new Set<string>();
  for (const leg of legs) {
    if (!Array.isArray(leg) || leg.length !== 2) {
      throw new Error("a leg is exactly two elements");
    }
    const [sell, buy] = leg as [unknown, unknown];
    for (const code of [sell, buy]) {
      if (typeof code !== "string" || code.length === 0) {
        throw new Error("a ticker is a non-empty string");
      }
    }
    if (sell === buy) {
      throw new Error("a leg cannot sell and buy the same ticker");
    }
    const key = (sell as string) + ">" + (buy as string);
    if (published.has(key)) {
      throw new Error("the leg " + key + " is published twice");
    }
    published.add(key);
    tickers.add(sell as string);
    tickers.add(buy as string);
    const outgoing = forward.get(sell as string) ?? [];
    outgoing.push(buy as string);
    forward.set(sell as string, outgoing);
  }

  const codes = Array.from(tickers).sort();
  const stranded: string[] = [];
  for (const start of codes) {
    const reached = new Set<string>();
    const queue = [start];
    while (queue.length > 0) {
      const node = queue.shift() as string;
      for (const next of forward.get(node) ?? []) {
        if (!reached.has(next)) {
          reached.add(next);
          queue.push(next);
        }
      }
    }
    for (const finish of codes) {
      if (finish !== start && !reached.has(finish)) {
        stranded.push(start + ">" + finish);
      }
    }
  }
  return stranded;
}
