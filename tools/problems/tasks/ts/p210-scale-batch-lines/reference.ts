const LINE = /^([1-9][0-9]*) (g|ml|each) ([A-Za-z]+(?: [A-Za-z]+)*)$/;
const TICK: Record<string, number> = { g: 1, ml: 5, each: 1 };

function wholePortion(value: number, base: number, want: number, tick: number): number {
  const top = value * want;
  const settled = Math.floor((2 * top + base * tick) / (2 * base * tick)) * tick;
  return settled === 0 ? tick : settled;
}

export function scaleBatchLines(
  items: string[],
  want: number,
  base: number,
): string[] {
  if (!Array.isArray(items)) {
    throw new Error("the sheet must be a list");
  }
  for (const portions of [want, base]) {
    if (typeof portions !== "number" || !Number.isInteger(portions) || portions < 1) {
      throw new Error("a portion count must be a whole number above zero");
    }
  }
  const named = new Set<string>();
  const out: string[] = [];
  for (const line of items) {
    if (typeof line !== "string") {
      throw new Error("every sheet line must be a string");
    }
    const hit = LINE.exec(line);
    if (hit === null) {
      throw new Error("the line breaks its shape: " + line);
    }
    const value = Number(hit[1]);
    const measure = hit[2];
    const name = hit[3];
    if (named.has(name)) {
      throw new Error("two lines name the same stuff: " + name);
    }
    named.add(name);
    const settled = wholePortion(value, base, want, TICK[measure]);
    out.push(settled + " " + measure + " " + name);
  }
  return out;
}
