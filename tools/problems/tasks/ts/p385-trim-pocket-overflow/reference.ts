export function trimPocketOverflow(owed: number[], ceiling: number): number[] {
  if (!Number.isInteger(ceiling) || ceiling < 0) {
    throw new Error("ceiling must be a whole number of cents, not below zero");
  }
  const handed: number[] = [];
  let tab = 0;
  for (const entry of owed) {
    if (!Number.isInteger(entry) || entry < 0) {
      throw new Error("every entry must be a whole number of cents, not below zero");
    }
    const room = ceiling - tab;
    const paid = entry < room ? entry : room;
    handed.push(paid);
    tab += paid;
  }
  return handed;
}
