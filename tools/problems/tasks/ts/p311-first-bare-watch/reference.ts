export function firstBareWatch(
  onDuty: string[][],
  warrants: string[][],
): number {
  if (!Array.isArray(onDuty) || onDuty.length === 0) {
    throw new Error("the duty list must be a non-empty list");
  }
  for (const watch of onDuty) {
    if (!Array.isArray(watch)) {
      throw new Error("every watch entry is a list");
    }
    for (const held of watch) {
      if (typeof held !== "string" || held.length === 0) {
        throw new Error("every warrant on watch is a non-empty name");
      }
    }
  }
  if (!Array.isArray(warrants) || warrants.length === 0) {
    throw new Error("the standing order must be a non-empty list");
  }
  const order: [string, number][] = [];
  const demanded = new Set<string>();
  for (const row of warrants) {
    if (!Array.isArray(row) || row.length !== 2) {
      throw new Error("every standing order row is a pair");
    }
    for (const field of row) {
      if (typeof field !== "string" || field.length === 0) {
        throw new Error("every standing order field is a non-empty string");
      }
    }
    if (!/^[0-9]+$/.test(row[1])) {
      throw new Error("a headcount is written in decimal figures");
    }
    const least = Number(row[1]);
    if (least < 1) {
      throw new Error("a standing order musters at least one hand");
    }
    if (demanded.has(row[0])) {
      throw new Error("that warrant is demanded twice over");
    }
    demanded.add(row[0]);
    order.push([row[0], least]);
  }

  for (let watch = 0; watch < onDuty.length; watch++) {
    const mustered = new Map<string, number>();
    for (const held of onDuty[watch]) {
      mustered.set(held, (mustered.get(held) ?? 0) + 1);
    }
    for (const [warrant, least] of order) {
      if ((mustered.get(warrant) ?? 0) < least) {
        return watch + 1;
      }
    }
  }
  return 0;
}
