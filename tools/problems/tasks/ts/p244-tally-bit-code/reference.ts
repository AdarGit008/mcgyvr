export function buildWeightCode(entries: any[]): any {
  if (!Array.isArray(entries) || entries.length === 0) {
    throw new Error("the entry list must hold at least one entry");
  }
  const tallyOf = new Map<string, number>();
  for (const entry of entries) {
    if (!Array.isArray(entry) || entry.length !== 2) {
      throw new Error("an entry must be a list of exactly two things");
    }
    const token = entry[0];
    const tally = entry[1];
    if (typeof token !== "string" || !/^[a-z]+$/.test(token)) {
      throw new Error("a token must be a non-empty string of lowercase letters");
    }
    if (tallyOf.has(token)) {
      throw new Error("a token shows up twice");
    }
    if (typeof tally !== "number" || !Number.isInteger(tally) || tally < 1) {
      throw new Error("a tally must be a whole number of one or more");
    }
    tallyOf.set(token, tally);
  }
  const tokens = [...tallyOf.keys()].sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));
  if (tokens.length === 1) {
    const only = tokens[0];
    const codes: Record<string, string> = {};
    codes[only] = "0";
    return { codes, bits: tallyOf.get(only), tallest: 1 };
  }
  const load: number[] = [];
  const near: number[] = [];
  const far: number[] = [];
  const holds: string[] = [];
  for (const token of tokens) {
    load.push(tallyOf.get(token) ?? 0);
    near.push(-1);
    far.push(-1);
    holds.push(token);
  }
  const live = new Set<number>();
  for (let i = 0; i < tokens.length; i++) live.add(i);
  const smallest = (): number => {
    let best = -1;
    for (const bud of live) {
      if (best === -1 || load[bud] < load[best] || (load[bud] === load[best] && bud < best)) {
        best = bud;
      }
    }
    live.delete(best);
    return best;
  };
  while (live.size > 1) {
    const first = smallest();
    const second = smallest();
    const fresh = load.length;
    load.push(load[first] + load[second]);
    near.push(first);
    far.push(second);
    holds.push("");
    live.add(fresh);
  }
  let crown = -1;
  for (const bud of live) crown = bud;
  const codes: Record<string, string> = {};
  const pending: [number, string][] = [[crown, ""]];
  while (pending.length > 0) {
    const step = pending.pop();
    if (step === undefined) break;
    const [bud, written] = step;
    if (near[bud] === -1) {
      codes[holds[bud]] = written;
      continue;
    }
    pending.push([far[bud], written + "1"]);
    pending.push([near[bud], written + "0"]);
  }
  let bits = 0;
  let tallest = 0;
  for (const token of tokens) {
    const width = codes[token].length;
    bits += (tallyOf.get(token) ?? 0) * width;
    if (width > tallest) tallest = width;
  }
  return { codes, bits, tallest };
}
