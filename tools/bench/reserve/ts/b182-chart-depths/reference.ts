/** Rung of every member of a crew chart, counting the chief as zero. */
export function chartDepths(chart: Record<string, string>): Record<string, number> {
  const rungs: Record<string, number> = {};
  for (const member of Object.keys(chart)) {
    const climbed: string[] = [];
    const climbing = new Set<string>();
    let at = member;
    while (at !== "" && rungs[at] === undefined) {
      if (climbing.has(at)) {
        throw new Error("the chart circles back at " + at);
      }
      if (chart[at] === undefined) {
        throw new Error("the chart does not list " + at);
      }
      climbing.add(at);
      climbed.push(at);
      at = chart[at];
    }
    let rung = at === "" ? -1 : rungs[at];
    for (let i = climbed.length - 1; i >= 0; i--) {
      rung += 1;
      rungs[climbed[i]] = rung;
    }
  }
  return rungs;
}
