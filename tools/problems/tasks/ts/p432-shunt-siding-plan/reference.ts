type Plan = { moves: string[]; blocked: string };

function isWhole(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

function codeSet(codes: string[], where: string): Set<string> {
  const seen = new Set<string>();
  for (const code of codes) {
    if (typeof code !== "string" || code.length === 0) {
      throw new Error("every car code is a non-empty string");
    }
    if (seen.has(code)) {
      throw new Error(where + " writes the code " + code + " twice");
    }
    seen.add(code);
  }
  return seen;
}

export function planShunting(
  arrival: string[],
  target: string[],
  depth: number,
): Plan {
  if (!Array.isArray(arrival) || !Array.isArray(target)) {
    throw new Error("planShunting expects two lists of car codes");
  }
  if (arrival.length === 0) {
    throw new Error("the arrival road holds no cars");
  }
  const standing = codeSet(arrival, "the arrival road");
  const wanted = codeSet(target, "the departure order");
  if (wanted.size !== standing.size) {
    throw new Error("the two lists do not name the same cars");
  }
  for (const code of wanted) {
    if (!standing.has(code)) {
      throw new Error("the two lists do not name the same cars");
    }
  }
  if (!isWhole(depth) || depth < 1) {
    throw new Error("the siding depth is a whole number of one or more");
  }

  const moves: string[] = [];
  const siding: string[] = [];
  let pulled = 0;
  let want = 0;
  while (want < target.length) {
    const top = siding.length === 0 ? null : siding[siding.length - 1];
    if (top !== null && top === target[want]) {
      siding.pop();
      moves.push("place " + top);
      want += 1;
      continue;
    }
    if (pulled >= arrival.length) {
      return { moves, blocked: "buried:" + target[want] };
    }
    if (siding.length >= depth) {
      return { moves, blocked: "full" };
    }
    siding.push(arrival[pulled]);
    moves.push("hold " + arrival[pulled]);
    pulled += 1;
  }
  return { moves, blocked: "" };
}
