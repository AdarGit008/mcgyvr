export function seatParties(rows: number[], parties: number[]): string[] {
  const used = rows.map(() => 0);
  const longest = rows.reduce((a, b) => (b > a ? b : a), 0);
  const records: string[] = [];
  for (const size of parties) {
    if (size < 1) {
      throw new Error("party size below 1");
    }
    if (size > longest) {
      records.push("rejected:too_big");
      continue;
    }
    let seated = false;
    for (let i = 0; i < rows.length; i++) {
      if (rows[i] - used[i] >= size) {
        records.push(`${i + 1}-${used[i] + 1}`);
        used[i] += size;
        seated = true;
        break;
      }
    }
    if (!seated) {
      records.push("rejected:full");
    }
  }
  return records;
}
