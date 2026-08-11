type Tally = { first: number; second: number; taken: number[] };

/** Play a row of cards out to the last card, each turn grabbing the better end. */
export function endGrab(cards: number[]): Tally {
  const row = [...cards];
  const taken: number[] = [];
  const totals = [0, 0];
  let turn = 0;
  while (row.length > 0) {
    const left = row[0];
    const right = row[row.length - 1];
    const card = left >= right ? left : right;
    if (left >= right) {
      row.shift();
    } else {
      row.pop();
    }
    taken.push(card);
    totals[turn] += card;
    turn = 1 - turn;
  }
  return { first: totals[0], second: totals[1], taken };
}
