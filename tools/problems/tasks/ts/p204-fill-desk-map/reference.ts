export function fillDeskMap(
  plan: string[],
  legend: Record<string, string[]>,
): Record<string, unknown> {
  if (!Array.isArray(plan) || plan.length === 0) {
    throw new Error("the floor must be a non-empty list of rows");
  }
  let width = -1;
  for (const row of plan) {
    if (typeof row !== "string" || row.length === 0) {
      throw new Error("every row must be a non-empty string");
    }
    if (width === -1) {
      width = row.length;
    } else if (row.length !== width) {
      throw new Error("the rows are not all the same length");
    }
    for (const ch of row) {
      if (ch !== "#" && ch !== "." && !(ch >= "a" && ch <= "z")) {
        throw new Error("stray character on the floor: " + ch);
      }
    }
  }
  if (typeof legend !== "object" || legend === null || Array.isArray(legend)) {
    throw new Error("the legend must be a mapping");
  }

  const desks = new Map<string, number[][]>();
  for (let r = 0; r < plan.length; r += 1) {
    for (let c = 0; c < plan[r].length; c += 1) {
      const ch = plan[r][c];
      if (ch >= "a" && ch <= "z") {
        if (!desks.has(ch)) desks.set(ch, []);
        (desks.get(ch) as number[][]).push([r, c]);
      }
    }
  }

  const grid = plan.map((row) => Array.from(row));
  const sat: string[] = [];
  const used = new Set<string>();
  let taken = 0;

  for (const label of Object.keys(legend).sort()) {
    if (!/^[a-z]$/.test(label)) {
      throw new Error("a bank letter must be exactly one small letter: " + label);
    }
    const spots = desks.get(label);
    if (spots === undefined) {
      throw new Error("the floor draws no bank " + label);
    }
    const names = legend[label];
    if (!Array.isArray(names)) {
      throw new Error("bank " + label + " must carry a list of people");
    }
    if (names.length > spots.length) {
      throw new Error("bank " + label + " has more people than desks");
    }
    for (let i = 0; i < names.length; i += 1) {
      const name = names[i];
      if (typeof name !== "string" || !/^[A-Za-z]+$/.test(name)) {
        throw new Error("a name must be a non-empty string of letters");
      }
      if (used.has(name)) {
        throw new Error("one name is handed two desks: " + name);
      }
      used.add(name);
      const [r, c] = spots[i];
      grid[r][c] = name[0].toUpperCase();
      sat.push(name + " r" + r + " c" + c);
      taken += 1;
    }
  }

  let total = 0;
  for (const spots of desks.values()) {
    total += spots.length;
  }
  return {
    floor: grid.map((row) => row.join("")),
    sat,
    spare: total - taken,
  };
}
