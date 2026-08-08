const TIERS = ["urgent", "soon", "routine"];
const WINDOWS = ["morning", "afternoon", "either"];
const PARTS = ["morning", "afternoon"];

type Patient = { name: string; tier: string; waited: number; window: string };
type Call = { slot: string; part: string };

export function assignFreedSlots(
  standby: Patient[],
  cancellations: Call[],
): { slot: string; name: string }[] {
  if (!Array.isArray(standby) || !Array.isArray(cancellations)) {
    throw new Error("assignFreedSlots expects two lists");
  }
  const names = new Set<string>();
  for (const one of standby) {
    if (one === null || typeof one !== "object" || typeof one.name !== "string") {
      throw new Error("a patient needs a name");
    }
    if (!TIERS.includes(one.tier) || !WINDOWS.includes(one.window)) {
      throw new Error("a patient needs a known tier and window: " + one.name);
    }
    if (!Number.isInteger(one.waited) || one.waited < 0) {
      throw new Error("waited is a whole number of zero or more");
    }
    if (names.has(one.name)) {
      throw new Error("two patients share the name " + one.name);
    }
    names.add(one.name);
  }
  const slots = new Set<string>();
  for (const call of cancellations) {
    if (call === null || typeof call !== "object" || typeof call.slot !== "string") {
      throw new Error("a cancellation needs a slot id");
    }
    if (!PARTS.includes(call.part)) {
      throw new Error("a cancellation names morning or afternoon");
    }
    if (slots.has(call.slot)) {
      throw new Error("two cancellations share the slot " + call.slot);
    }
    slots.add(call.slot);
  }
  const placed = new Set<string>();
  const placements: { slot: string; name: string }[] = [];
  for (const call of cancellations) {
    let winner: Patient | null = null;
    for (const one of standby) {
      if (placed.has(one.name)) {
        continue;
      }
      if (one.window !== call.part && one.window !== "either") {
        continue;
      }
      if (winner === null) {
        winner = one;
        continue;
      }
      const here = TIERS.indexOf(one.tier);
      const there = TIERS.indexOf(winner.tier);
      if (here < there || (here === there && one.waited > winner.waited)) {
        winner = one;
      }
    }
    if (winner === null) {
      continue;
    }
    placed.add(winner.name);
    placements.push({ slot: call.slot, name: winner.name });
  }
  return placements;
}
