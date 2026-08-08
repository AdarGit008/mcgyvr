const PLAN: Record<string, { stem: string; blocks: number[] }> = {
  kv: { stem: "0", blocks: [3, 3, 3] },
  mr: { stem: "07", blocks: [4, 4] },
  ts: { stem: "+31", blocks: [2, 4, 4] },
  wd: { stem: "", blocks: [3, 4] },
};

export function formatSubscriberNumber(region: string, digits: string): string {
  if (typeof region !== "string" || !Object.prototype.hasOwnProperty.call(PLAN, region)) {
    throw new Error("the region is not one this plan knows");
  }
  if (typeof digits !== "string") {
    throw new Error("the digits must be a string");
  }
  if (!/^[0-9]+$/.test(digits)) {
    throw new Error("the digits must be nothing but digits");
  }
  const plan = PLAN[region];
  const wanted = plan.blocks.reduce((sum, block) => sum + block, 0);
  if (digits.length !== wanted) {
    throw new Error("the region wants exactly " + wanted + " digits");
  }
  if (digits.slice(0, 1) === "0") {
    throw new Error("a subscriber number never opens with a nought");
  }
  const parts: string[] = [];
  let cursor = 0;
  for (const block of plan.blocks) {
    parts.push(digits.slice(cursor, cursor + block));
    cursor += block;
  }
  const body = parts.join(" ");
  return plan.stem === "" ? body : plan.stem + " " + body;
}
