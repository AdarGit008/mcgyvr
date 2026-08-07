export function rankWithPolicy(
  scores: number[],
  policy: string,
  direction: string,
): number[] {
  if (!["dense", "gapped", "entry"].includes(policy)) {
    throw new Error("bad policy");
  }
  if (!["asc", "desc"].includes(direction)) {
    throw new Error("bad direction");
  }
  if (!Array.isArray(scores) || scores.length === 0) {
    throw new Error("empty scores");
  }
  for (const s of scores) {
    if (typeof s !== "number" || !Number.isInteger(s)) {
      throw new Error("non-integer score");
    }
  }
  const sign = direction === "asc" ? 1 : -1;
  if (policy === "entry") {
    const order = scores.map((_, i) => i);
    order.sort((a, b) => sign * (scores[a] - scores[b]) || a - b);
    const out = new Array(scores.length).fill(0);
    order.forEach((original, r) => {
      out[original] = r + 1;
    });
    return out;
  }
  const distinct = [...new Set(scores)].sort((a, b) => sign * (a - b));
  const rank = new Map<number, number>();
  if (policy === "dense") {
    distinct.forEach((v, i) => rank.set(v, i + 1));
  } else {
    for (const v of distinct) {
      let better = 0;
      for (const s of scores) {
        if (sign * (s - v) < 0) {
          better += 1;
        }
      }
      rank.set(v, better + 1);
    }
  }
  return scores.map((s) => rank.get(s) as number);
}
