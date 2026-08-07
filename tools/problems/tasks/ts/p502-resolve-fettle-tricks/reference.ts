const CARD = /^[bcfl](?:[1-9]|1[0-3])$/;
const CARRIES: Record<number, number> = { 10: 1, 11: 2, 12: 3, 13: 4, 1: 5 };

function height(strength: number): number {
  return strength === 1 ? 14 : strength;
}

export function resolveFettleTricks(
  deal: Record<string, unknown>,
): Record<string, unknown> {
  if (deal === null || typeof deal !== "object" || Array.isArray(deal)) {
    throw new Error("the deal must be a mapping");
  }
  const trump = deal.trump;
  if (typeof trump !== "string" || !["b", "c", "f", "l", "none"].includes(trump)) {
    throw new Error("trump must be a house letter or the word none");
  }
  const tricks = deal.tricks;
  if (!Array.isArray(tricks) || tricks.length === 0) {
    throw new Error("tricks must be a non-empty list");
  }

  const laid = new Set<string>();
  const parsed: Array<Array<{ house: string; strength: number }>> = [];
  for (const trick of tricks) {
    if (!Array.isArray(trick) || trick.length !== 4) {
      throw new Error("a trick must be a list of exactly four cards");
    }
    const row: Array<{ house: string; strength: number }> = [];
    for (const card of trick) {
      if (typeof card !== "string" || !CARD.test(card)) {
        throw new Error("a card must be a house letter and a strength from 1 to 13");
      }
      if (laid.has(card)) {
        throw new Error("a card is laid twice in the deal");
      }
      laid.add(card);
      row.push({ house: card.slice(0, 1), strength: Number(card.slice(1)) });
    }
    parsed.push(row);
  }

  const takers: number[] = [];
  const worths: number[] = [];
  const banked = [0, 0, 0, 0];
  let leader = 0;
  for (let index = 0; index < parsed.length; index++) {
    const row = parsed[index];
    const called = row[0].house;
    const wanted = trump !== "none" && row.some((card) => card.house === trump)
      ? trump
      : called;
    let best = 0;
    for (let place = 1; place < 4; place++) {
      if (row[place].house !== wanted) continue;
      if (row[best].house !== wanted || height(row[place].strength) > height(row[best].strength)) {
        best = place;
      }
    }
    let worth = 0;
    for (const card of row) worth += CARRIES[card.strength] ?? 0;
    if (index === parsed.length - 1) worth += 3;
    const taker = (leader + best) % 4;
    takers.push(taker);
    worths.push(worth);
    banked[taker] += worth;
    leader = taker;
  }

  return {
    takers,
    worths,
    even: banked[0] + banked[2],
    odd: banked[1] + banked[3],
  };
}
