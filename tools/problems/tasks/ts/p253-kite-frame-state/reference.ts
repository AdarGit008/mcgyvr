export function kiteFrameState(
  rallies: string[],
): { left: number; right: number; winner: string } {
  if (!Array.isArray(rallies)) {
    throw new Error("kiteFrameState expects a list of rally winners");
  }
  const score: Record<string, number> = { left: 0, right: 0 };
  let winner = "";
  for (const rally of rallies) {
    if (rally !== "left" && rally !== "right") {
      throw new Error(`unknown side ${String(rally)}`);
    }
    if (winner !== "") {
      continue;
    }
    score[rally] += 1;
    const other = rally === "left" ? "right" : "left";
    const ahead = score[rally] - score[other];
    if ((score[rally] >= 15 && ahead >= 2) || score[rally] >= 20) {
      winner = rally;
    }
  }
  return { left: score.left, right: score.right, winner };
}
