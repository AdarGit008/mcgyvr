/** Where each ruled library should land. */
type Pair = [number, number];
type Release = { text: string; pair: Pair };
type Rule = { package: string; min: Pair; max: Pair };

function mapping(value: unknown): boolean {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function readRelease(text: unknown): Pair {
  if (typeof text !== "string") {
    throw new Error("a release must be a string");
  }
  const parts = text.split(".");
  if (parts.length !== 2) {
    throw new Error("a release must have two groups");
  }
  const pair: number[] = [];
  for (const part of parts) {
    if (!/^\d+$/.test(part)) {
      throw new Error("a release group must be digits");
    }
    if (part.length > 1 && part.startsWith("0")) {
      throw new Error("a release group must not carry a leading zero");
    }
    pair.push(Number(part));
  }
  return [pair[0], pair[1]];
}

function rank(left: Pair, right: Pair): number {
  if (left[0] !== right[0]) {
    return left[0] - right[0];
  }
  return left[1] - right[1];
}

export function chooseUpgrades(
  request: Record<string, unknown>
): Record<string, unknown> {
  if (!mapping(request)) {
    throw new Error("the request must be a mapping");
  }
  const rawInstalled = request.installed;
  const rawOffers = request.offers;
  const rawRules = request.rules;
  if (!mapping(rawInstalled)) {
    throw new Error("installed must be a mapping");
  }
  if (!mapping(rawOffers)) {
    throw new Error("offers must be a mapping");
  }
  if (!Array.isArray(rawRules)) {
    throw new Error("rules must be a list");
  }

  const carried = new Map<string, Release[]>();
  for (const [name, listed] of Object.entries(
    rawOffers as Record<string, unknown>
  )) {
    if (!Array.isArray(listed) || listed.length === 0) {
      throw new Error("an offers entry must be a non-empty list");
    }
    const texts = new Set<string>();
    const releases: Release[] = [];
    for (const text of listed) {
      const pair = readRelease(text);
      if (texts.has(text as string)) {
        throw new Error("an offers entry repeats a release");
      }
      texts.add(text as string);
      releases.push({ text: text as string, pair });
    }
    carried.set(name, releases);
  }

  const running = new Map<string, Release>();
  for (const [name, text] of Object.entries(
    rawInstalled as Record<string, unknown>
  )) {
    if (!carried.has(name)) {
      throw new Error("a library running today is not carried by the registry");
    }
    running.set(name, { text: text as string, pair: readRelease(text) });
  }

  const bounds = new Map<string, Rule[]>();
  for (const raw of rawRules) {
    if (!mapping(raw)) {
      throw new Error("a rule must be a mapping");
    }
    const record = raw as Record<string, unknown>;
    const name = record.package;
    if (typeof name !== "string" || !carried.has(name)) {
      throw new Error("a rule bounds a library the registry does not carry");
    }
    const low = readRelease(record.min);
    const high = readRelease(record.max);
    if (rank(low, high) > 0) {
      throw new Error("a rule's min is above its max");
    }
    const rule: Rule = { package: name, min: low, max: high };
    const already = bounds.get(name);
    if (already === undefined) {
      bounds.set(name, [rule]);
    } else {
      already.push(rule);
    }
  }

  const moves: Record<string, string>[] = [];
  const snags: Record<string, string>[] = [];
  for (const name of Array.from(bounds.keys()).sort()) {
    const rules = bounds.get(name) as Rule[];
    const allowed = (carried.get(name) as Release[]).filter((release) =>
      rules.every(
        (rule) =>
          rank(release.pair, rule.min) >= 0 && rank(release.pair, rule.max) <= 0
      )
    );
    const lowest = (pool: Release[]): Release =>
      pool.reduce((best, release) =>
        rank(release.pair, best.pair) < 0 ? release : best
      );
    const here = running.get(name);
    if (here === undefined) {
      if (allowed.length === 0) {
        snags.push({ package: name, why: "none" });
      } else {
        moves.push({ package: name, to: lowest(allowed).text, action: "fetch" });
      }
      continue;
    }
    if (allowed.some((release) => rank(release.pair, here.pair) === 0)) {
      moves.push({ package: name, to: here.text, action: "hold" });
      continue;
    }
    const above = allowed.filter((release) => rank(release.pair, here.pair) > 0);
    if (above.length > 0) {
      moves.push({ package: name, to: lowest(above).text, action: "lift" });
    } else if (allowed.length > 0) {
      snags.push({ package: name, why: "drop" });
    } else {
      snags.push({ package: name, why: "none" });
    }
  }
  return { moves, snags };
}
