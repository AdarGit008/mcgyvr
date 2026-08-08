const HOUSE_WEIGHT: Record<string, number> = { m: 4, r: 3, s: 2, v: 1 };
const STRENGTH: Record<string, number> = {
  monolith: 5,
  prism: 4,
  chain: 3,
  echo: 2,
  twin: 1,
  drift: 0,
};

function walk(a: number[], b: number[]): number {
  const shared = Math.min(a.length, b.length);
  for (let i = 0; i < shared; i++) {
    if (a[i] !== b[i]) return b[i] - a[i];
  }
  return 0;
}

export function orderSkeinHands(hands: any[]): any {
  if (!Array.isArray(hands) || hands.length === 0) {
    throw new Error("the argument must be a list holding at least one hand");
  }
  const graded: { grade: string; ladder: number[]; weights: number[]; at: number }[] = [];
  for (let at = 0; at < hands.length; at++) {
    const hand = hands[at];
    if (!Array.isArray(hand) || hand.length !== 5) {
      throw new Error("a hand must be a list of exactly five cards");
    }
    const pips: number[] = [];
    const weights: number[] = [];
    const houses = new Set<string>();
    const written = new Set<string>();
    for (const card of hand) {
      if (typeof card !== "string" || !/^(10|[1-9])[mrsv]$/.test(card)) {
        throw new Error("a card must be a pip from 1 to 10 and one house letter");
      }
      if (written.has(card)) {
        throw new Error("a hand writes the same card twice");
      }
      written.add(card);
      const house = card.slice(card.length - 1);
      pips.push(Number(card.slice(0, card.length - 1)));
      weights.push(HOUSE_WEIGHT[house]);
      houses.add(house);
    }
    const carried = new Map<number, number>();
    for (const pip of pips) carried.set(pip, (carried.get(pip) ?? 0) + 1);
    const ladder = [...carried.keys()].sort((a, b) => {
      const countA = carried.get(a) ?? 0;
      const countB = carried.get(b) ?? 0;
      return countB - countA || b - a;
    });
    const span = Math.max(...pips) - Math.min(...pips);
    let grade = "drift";
    if (ladder.length === 2) grade = "monolith";
    else if (ladder.length === 5 && houses.size === 4) grade = "prism";
    else if (ladder.length === 5 && span === 4) grade = "chain";
    else if (ladder.length === 3) grade = "echo";
    else if (ladder.length === 4) grade = "twin";
    graded.push({
      grade,
      ladder,
      weights: weights.slice().sort((a, b) => b - a),
      at,
    });
  }
  const ranked = graded.slice().sort(
    (x, y) =>
      STRENGTH[y.grade] - STRENGTH[x.grade] ||
      walk(x.ladder, y.ladder) ||
      walk(x.weights, y.weights) ||
      x.at - y.at,
  );
  return {
    grades: graded.map((entry) => entry.grade),
    order: ranked.map((entry) => entry.at),
  };
}
