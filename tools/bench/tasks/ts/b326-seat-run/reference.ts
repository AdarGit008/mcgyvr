export function seatRun(row: string, party: number): number {
  let run = 0;
  for (let i = 0; i < row.length; i += 1) {
    run = row[i] === "." ? run + 1 : 0;
    if (run === party) {
      return i - party + 1;
    }
  }
  return -1;
}
