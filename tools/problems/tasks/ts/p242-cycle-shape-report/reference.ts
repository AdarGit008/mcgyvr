function greatestCommon(a: number, b: number): number {
  let x = a;
  let y = b;
  while (y !== 0) {
    const next = x % y;
    x = y;
    y = next;
  }
  return x;
}

export function cycleShapeReport(chart: number[]): any {
  if (!Array.isArray(chart) || chart.length === 0) {
    throw new Error("the chart must be a non-empty list");
  }
  const seats = chart.length;
  const named = new Set<number>();
  for (const entry of chart) {
    if (typeof entry !== "number" || !Number.isInteger(entry)) {
      throw new Error("every entry must be a whole number");
    }
    if (entry < 0 || entry >= seats) {
      throw new Error("entry names a seat outside the chart");
    }
    if (named.has(entry)) {
      throw new Error("two entries name the same seat");
    }
    named.add(entry);
  }
  const traced = new Array(seats).fill(false);
  const loops: number[][] = [];
  for (let start = 0; start < seats; start++) {
    if (traced[start]) continue;
    const loop: number[] = [];
    let at = start;
    while (!traced[at]) {
      traced[at] = true;
      loop.push(at);
      at = chart[at];
    }
    loops.push(loop);
  }
  const widths = loops.map((loop) => loop.length).sort((a, b) => b - a);
  let repeat = 1;
  for (const width of widths) {
    repeat = (repeat / greatestCommon(repeat, width)) * width;
  }
  const swing = (seats - loops.length) % 2 === 0 ? "even" : "odd";
  return { loops, widths, repeat, swing };
}
