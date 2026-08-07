export function flatlineSpans(channel: number[], least: number): number[][] {
  if (!Number.isInteger(least) || least < 2) {
    throw new Error("least must be a whole number of at least two");
  }
  const spans: number[][] = [];
  let start = 0;
  for (let at = 1; at <= channel.length; at++) {
    if (at === channel.length || channel[at] !== channel[at - 1]) {
      if (at - start >= least) {
        spans.push([start, at - 1]);
      }
      start = at;
    }
  }
  return spans;
}
