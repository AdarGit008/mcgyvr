type Tally = { winner: string; bands: number[]; points: number[]; serve: string };

export function replayTesselMatch(rallies: string[]): Tally {
  if (!Array.isArray(rallies)) {
    throw new Error("replayTesselMatch expects a list of rally winners");
  }
  const bands: Record<string, number> = { A: 0, B: 0 };
  let points: Record<string, number> = { A: 0, B: 0 };
  let serve = "A";
  let winner = "";
  for (const rally of rallies) {
    if (rally !== "A" && rally !== "B") {
      throw new Error("a rally winner is either A or B");
    }
    if (winner !== "") {
      throw new Error("the match is already decided");
    }
    const other = rally === "A" ? "B" : "A";
    if (rally !== serve) {
      serve = rally;
      continue;
    }
    points[rally] += 1;
    const mine = points[rally];
    const theirs = points[other];
    if ((mine >= 7 && mine - theirs >= 2) || mine >= 10) {
      bands[rally] += 1;
      if (bands[rally] === 3) {
        winner = rally;
        serve = "";
      } else {
        points = { A: 0, B: 0 };
        serve = other;
      }
    }
  }
  return {
    winner,
    bands: [bands.A, bands.B],
    points: [points.A, points.B],
    serve,
  };
}
