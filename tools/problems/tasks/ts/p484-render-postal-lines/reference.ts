const PLANS: Record<string, string[][]> = {
  vela: [["who"], ["house", "street"], ["code", "town"]],
  korrin: [["who"], ["street", "house"], ["town"], ["code"]],
  mebis: [["who"], ["ward"], ["street", "house"], ["town", "code"]],
};

const SHOUTED: Record<string, string[]> = {
  vela: ["town"],
  korrin: ["who", "code"],
  mebis: ["who", "ward", "street", "house", "town", "code"],
};

function tidy(value: unknown): string {
  if (typeof value !== "string") {
    return "";
  }
  return value.trim().replace(/ +/g, " ");
}

export function renderPostalLines(entry: any, region: string): string[] {
  if (typeof entry !== "object" || entry === null || Array.isArray(entry)) {
    throw new Error("entry must be a record");
  }
  const plan = Object.prototype.hasOwnProperty.call(PLANS, region)
    ? PLANS[region]
    : undefined;
  if (plan === undefined) {
    throw new Error(`${String(region)} is not one of vela, korrin, mebis`);
  }
  const shouted = new Set(SHOUTED[region]);
  const lines: string[] = [];
  for (const slots of plan) {
    const pieces: string[] = [];
    for (const slot of slots) {
      const value = tidy(entry[slot]);
      if (value === "") {
        throw new Error(`${region} needs ${slot} and it is missing`);
      }
      pieces.push(shouted.has(slot) ? value.toUpperCase() : value);
    }
    lines.push(pieces.join(" "));
  }
  return lines;
}
