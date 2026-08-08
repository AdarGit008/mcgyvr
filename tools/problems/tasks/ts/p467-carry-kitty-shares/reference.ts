function whole(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

export function carryKittyShares(
  hops: Record<string, unknown>[],
): { each: number[]; left: number } {
  if (!Array.isArray(hops)) {
    throw new Error("carryKittyShares expects a list of hops");
  }
  if (hops.length === 0) {
    throw new Error("the journey has no hops");
  }

  const each: number[] = [];
  let kitty = 0;
  for (const hop of hops) {
    if (typeof hop !== "object" || hop === null || Array.isArray(hop)) {
      throw new Error("a hop is not a mapping");
    }
    if (Object.keys(hop).sort().join(",") !== "cents,heads") {
      throw new Error("a hop carries exactly cents and heads");
    }
    const cents = hop["cents"];
    const heads = hop["heads"];
    if (!whole(cents) || Number(cents) < 0) {
      throw new Error("a hop's cents are not whole or fall below nought");
    }
    if (!whole(heads) || Number(heads) < 1) {
      throw new Error("a hop's heads are not whole or fall below one");
    }
    kitty += Number(cents);
    const share = Math.floor(kitty / Number(heads));
    each.push(share);
    kitty -= share * Number(heads);
  }
  return { each, left: kitty };
}
