const WEIGHT_LIMIT = 10000;

function band(width: number, what: string): void {
  if (!Number.isInteger(width) || width < 1 || width > 1000) {
    throw new Error(`${what} must be a whole number between 1 and 1000`);
  }
}

function readBag(bag: number[][], head: number, tail: number): number[][] {
  if (!Array.isArray(bag)) {
    throw new Error("a bag must be a list");
  }
  const seen = new Set<string>();
  const links: number[][] = [];
  for (const link of bag) {
    if (!Array.isArray(link) || link.length !== 3) {
      throw new Error("every link must be a triple");
    }
    const from = link[0];
    const to = link[1];
    const weight = link[2];
    if (!Number.isInteger(from) || from < 0 || from >= head) {
      throw new Error("an endpoint lies outside its band");
    }
    if (!Number.isInteger(to) || to < 0 || to >= tail) {
      throw new Error("an endpoint lies outside its band");
    }
    if (!Number.isInteger(weight) || Math.abs(weight) > WEIGHT_LIMIT) {
      throw new Error("a weight must be a whole number within the size limit");
    }
    if (weight === 0) {
      throw new Error("a bag may not store a weight of nothing");
    }
    const pair = `${from}:${to}`;
    if (seen.has(pair)) {
      throw new Error("a bag holds two links between the same endpoints");
    }
    seen.add(pair);
    links.push([from, to, weight]);
  }
  return links;
}

export function tripletChainCells(
  first: number[][],
  second: number[][],
  lefts: number,
  mids: number,
  rights: number,
): number[][] {
  band(lefts, "lefts");
  band(mids, "mids");
  band(rights, "rights");

  const ones = readBag(first, lefts, mids);
  const twos = readBag(second, mids, rights);

  const leaving = new Map<number, number[][]>();
  for (const link of twos) {
    const bucket = leaving.get(link[0]);
    if (bucket === undefined) {
      leaving.set(link[0], [link]);
    } else {
      bucket.push(link);
    }
  }

  const routes = new Map<string, number>();
  for (const [source, middle, weight] of ones) {
    for (const onward of leaving.get(middle) ?? []) {
      const pair = `${source}:${onward[1]}`;
      routes.set(pair, (routes.get(pair) ?? 0) + weight * onward[2]);
    }
  }

  const out: number[][] = [];
  for (const [pair, weight] of routes) {
    if (weight === 0) {
      continue;
    }
    const cut = pair.indexOf(":");
    out.push([
      Number(pair.slice(0, cut)),
      Number(pair.slice(cut + 1)),
      weight + 0,
    ]);
  }
  out.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  return out;
}
