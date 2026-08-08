export function parseDuration(input: string): number {
  if (typeof input !== "string") {
    throw new Error("parseDuration expects a string");
  }
  if (!/^(?:\d+[dhms])+$/.test(input)) {
    throw new Error("malformed duration");
  }
  const seconds: Record<string, number> = { d: 86400, h: 3600, m: 60, s: 1 };
  const rank = ["d", "h", "m", "s"];
  const units: string[] = [];
  let total = 0;
  for (const pair of input.matchAll(/(\d+)([dhms])/g)) {
    units.push(pair[2]);
    total += Number(pair[1]) * seconds[pair[2]];
  }
  for (let i = 1; i < units.length; i++) {
    if (rank.indexOf(units[i]) <= rank.indexOf(units[i - 1])) {
      throw new Error("units out of order or repeated");
    }
  }
  return total;
}
