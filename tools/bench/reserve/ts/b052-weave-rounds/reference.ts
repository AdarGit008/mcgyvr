export function widestList(lanes: unknown[][]): number {
  let widest = 0;
  for (const lane of lanes) {
    if (lane.length > widest) {
      widest = lane.length;
    }
  }
  return widest;
}

export function weaveRounds(lanes: unknown[][]): unknown[] {
  if (!Array.isArray(lanes)) {
    throw new Error("weaveRounds expects a list of lanes");
  }
  for (const lane of lanes) {
    if (!Array.isArray(lane)) {
      throw new Error("every lane must be a list");
    }
  }
  const woven: unknown[] = [];
  for (let round = 0; round < widestList(lanes); round++) {
    for (const lane of lanes) {
      if (round < lane.length) {
        woven.push(lane[round]);
      }
    }
  }
  return woven;
}
