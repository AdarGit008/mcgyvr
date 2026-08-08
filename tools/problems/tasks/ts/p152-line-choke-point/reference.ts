export function lineChokePoint(
  stations: Array<[string, number, number]>,
): { station: string; output: number } {
  if (!Array.isArray(stations) || stations.length === 0) {
    throw new Error("empty station list");
  }
  const seen = new Set<string>();
  let bestName = "";
  let bestOutput = -1;
  for (const entry of stations) {
    if (!Array.isArray(entry) || entry.length !== 3) {
      throw new Error("malformed station");
    }
    const [name, machines, rate] = entry;
    if (typeof name !== "string" || name === "") {
      throw new Error("bad station name");
    }
    if (typeof machines !== "number" || !Number.isInteger(machines) || machines < 1) {
      throw new Error("bad machine count");
    }
    if (typeof rate !== "number" || !Number.isInteger(rate) || rate < 1) {
      throw new Error("bad rate");
    }
    if (seen.has(name)) {
      throw new Error("duplicate station name");
    }
    seen.add(name);
    const output = machines * rate;
    if (bestOutput === -1 || output < bestOutput) {
      bestOutput = output;
      bestName = name;
    }
  }
  return { station: bestName, output: bestOutput };
}
