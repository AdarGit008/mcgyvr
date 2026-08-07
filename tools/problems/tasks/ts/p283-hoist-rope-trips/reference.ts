function whole(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

export function planHoistTrips(
  hoists: { tag: string; level: number }[],
  stops: number[],
): string[] {
  if (!Array.isArray(hoists) || hoists.length === 0) {
    throw new Error("hoists must be a non-empty list");
  }
  if (!Array.isArray(stops)) {
    throw new Error("stops must be a list");
  }
  const order: string[] = [];
  const rests = new Map<string, number>();
  const spent = new Map<string, number>();
  for (const hoist of hoists) {
    if (hoist === null || typeof hoist !== "object") {
      throw new Error("a hoist must be a record");
    }
    const tag = hoist.tag;
    if (typeof tag !== "string" || tag.length === 0 || tag === "idle") {
      throw new Error("a tag must be a non-empty string other than idle");
    }
    if (rests.has(tag)) {
      throw new Error("tags repeat: " + tag);
    }
    if (!whole(hoist.level) || hoist.level < 0) {
      throw new Error("resting level must be an integer of at least 0: " + tag);
    }
    order.push(tag);
    rests.set(tag, hoist.level);
    spent.set(tag, 0);
  }
  for (const stop of stops) {
    if (!whole(stop) || stop < 0) {
      throw new Error("a stop must be an integer of at least 0");
    }
  }

  const sheet: string[] = [];
  for (const stop of stops) {
    let chosen = "";
    let least = 0;
    for (const tag of order) {
      if ((spent.get(tag) as number) >= 12) {
        continue;
      }
      const at = rests.get(tag) as number;
      const cost = stop > at ? 2 * (stop - at) : at - stop;
      if (chosen === "" || cost < least || (cost === least && tag < chosen)) {
        chosen = tag;
        least = cost;
      }
    }
    if (chosen === "") {
      sheet.push("idle");
      continue;
    }
    spent.set(chosen, (spent.get(chosen) as number) + least);
    rests.set(chosen, stop);
    sheet.push(chosen);
  }
  return sheet;
}
