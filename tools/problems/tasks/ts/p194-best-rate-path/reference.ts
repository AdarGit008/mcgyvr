const MILLION = 1000000;

type Best = { amount: number; path: string[] };

function beats(candidate: Best, incumbent: Best | null): boolean {
  if (incumbent === null) {
    return true;
  }
  if (candidate.amount !== incumbent.amount) {
    return candidate.amount > incumbent.amount;
  }
  if (candidate.path.length !== incumbent.path.length) {
    return candidate.path.length < incumbent.path.length;
  }
  for (let i = 0; i < candidate.path.length; i++) {
    if (candidate.path[i] !== incumbent.path[i]) {
      return candidate.path[i] < incumbent.path[i];
    }
  }
  return false;
}

export function bestRatePath(
  quotes: unknown[][],
  amount: number,
  source: string,
  destination: string
): Record<string, unknown> {
  if (!Array.isArray(quotes) || quotes.length === 0) {
    throw new Error("no quotes were supplied");
  }
  const edges = new Map<string, Array<[string, number]>>();
  const seen = new Set<string>();
  const known = new Set<string>();
  for (const quote of quotes) {
    if (!Array.isArray(quote) || quote.length !== 3) {
      throw new Error("a quote is three elements");
    }
    const [base, counter, micro] = quote as [unknown, unknown, unknown];
    for (const code of [base, counter]) {
      if (typeof code !== "string" || code.length === 0) {
        throw new Error("a currency code is a non-empty string");
      }
    }
    if (base === counter) {
      throw new Error("a quote cannot name one code on both sides");
    }
    if (!Number.isInteger(micro) || (micro as number) <= 0) {
      throw new Error("micro must be a positive whole number");
    }
    const key = (base as string) + ">" + (counter as string);
    if (seen.has(key)) {
      throw new Error("the ordered pair " + key + " is quoted twice");
    }
    seen.add(key);
    known.add(base as string);
    known.add(counter as string);
    const outgoing = edges.get(base as string) ?? [];
    outgoing.push([counter as string, micro as number]);
    edges.set(base as string, outgoing);
  }
  if (!Number.isInteger(amount) || amount <= 0) {
    throw new Error("the amount must be a positive whole number");
  }
  if (typeof source !== "string" || typeof destination !== "string") {
    throw new Error("source and destination are currency codes");
  }
  if (source === destination) {
    throw new Error("a run must move between two different codes");
  }
  for (const code of [source, destination]) {
    if (!known.has(code)) {
      throw new Error("no quote names " + code);
    }
  }

  let best: Best | null = null;
  const path: string[] = [source];
  const onPath = new Set<string>([source]);

  const walk = (node: string, value: number): void => {
    if (node === destination) {
      const candidate = { amount: value, path: path.slice() };
      if (beats(candidate, best)) {
        best = candidate;
      }
      return;
    }
    for (const [next, micro] of edges.get(node) ?? []) {
      if (onPath.has(next)) {
        continue;
      }
      onPath.add(next);
      path.push(next);
      walk(next, Math.floor((value * micro) / MILLION));
      path.pop();
      onPath.delete(next);
    }
  };
  walk(source, amount);

  if (best === null) {
    throw new Error("no run connects " + source + " to " + destination);
  }
  const found = best as Best;
  return { amount: found.amount, path: found.path };
}
