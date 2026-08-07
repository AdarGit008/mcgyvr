/** Who took one Vane trick, and which seats reneged on the called plume. */
export function judgeVaneTrick(play: Record<string, unknown>): Record<string, unknown> {
  if (play === null || typeof play !== "object" || Array.isArray(play)) {
    throw new Error("the play must be a mapping");
  }
  const trump = play.trump;
  if (typeof trump !== "string" || !["k", "n", "p", "t", "bare"].includes(trump)) {
    throw new Error("trump must be a plume letter or the word bare");
  }
  const lead = play.lead;
  if (typeof lead !== "number" || !Number.isInteger(lead) || lead < 0 || lead > 3) {
    throw new Error("lead must be a seat from 0 to 3");
  }
  const holdings = play.holdings;
  if (!Array.isArray(holdings) || holdings.length !== 4) {
    throw new Error("holdings must be a list of exactly four holdings");
  }
  const seen = new Set<string>();
  for (const holding of holdings) {
    if (!Array.isArray(holding) || holding.length === 0) {
      throw new Error("a holding must be a non-empty list of cards");
    }
    for (const card of holding) {
      if (typeof card !== "string" || !/^[2-9][knpt]$/.test(card)) {
        throw new Error("a card must be a heat from 2 to 9 and a plume letter");
      }
      if (seen.has(card)) {
        throw new Error("one card sits in two holdings");
      }
      seen.add(card);
    }
  }
  const played = play.played;
  if (!Array.isArray(played) || played.length !== 4) {
    throw new Error("played must be a list of exactly four cards");
  }
  const seats: number[] = [];
  for (let place = 0; place < 4; place++) {
    const card = played[place];
    if (typeof card !== "string" || !/^[2-9][knpt]$/.test(card)) {
      throw new Error("a card must be a heat from 2 to 9 and a plume letter");
    }
    const seat = (lead + place) % 4;
    if (!(holdings[seat] as string[]).includes(card)) {
      throw new Error("a seat laid a card it never held");
    }
    seats.push(seat);
  }

  const called = (played[0] as string).slice(1);
  const revokes: number[] = [];
  for (let place = 1; place < 4; place++) {
    const card = played[place] as string;
    if (card.slice(1) === called) continue;
    if ((holdings[seats[place]] as string[]).some((held) => held.slice(1) === called)) {
      revokes.push(seats[place]);
    }
  }
  revokes.sort((a, b) => a - b);

  const standing: number[] = [];
  for (let place = 0; place < 4; place++) {
    if (!revokes.includes(seats[place])) standing.push(place);
  }
  const wanted =
    trump !== "bare" && standing.some((place) => (played[place] as string).slice(1) === trump)
      ? trump
      : called;
  let best = -1;
  for (const place of standing) {
    if ((played[place] as string).slice(1) !== wanted) continue;
    if (best < 0 || Number((played[place] as string).slice(0, 1)) > Number((played[best] as string).slice(0, 1))) {
      best = place;
    }
  }

  return { taker: seats[best], revokes };
}
