/** Drain labelled items across planned lanes, round by round. */
export function drainLanes(
  plan: [string, number][],
  items: [string, string][],
): { order: string[]; rounds: number } {
  if (!Array.isArray(plan)) {
    throw new Error("the plan must be a list");
  }
  if (plan.length === 0) {
    throw new Error("the plan must not be empty");
  }
  const queues = new Map<string, string[]>();
  for (const entry of plan) {
    if (!Array.isArray(entry) || entry.length !== 2) {
      throw new Error("each plan entry must be a lane and a quota");
    }
    const [lane, quota] = entry;
    if (typeof lane !== "string" || lane === "") {
      throw new Error("each lane must be a non-empty string");
    }
    if (!Number.isInteger(quota) || quota < 1) {
      throw new Error("each quota must be a positive integer");
    }
    if (queues.has(lane)) {
      throw new Error(`lane declared twice: ${lane}`);
    }
    queues.set(lane, []);
  }
  let remaining = 0;
  for (const item of items) {
    if (!Array.isArray(item) || item.length !== 2) {
      throw new Error("each item must be a label and a lane");
    }
    const [label, lane] = item;
    if (typeof label !== "string") {
      throw new Error("each label must be a string");
    }
    if (typeof lane !== "string") {
      throw new Error("each item lane must be a string");
    }
    const queue = queues.get(lane);
    if (queue === undefined) {
      throw new Error(`item for an undeclared lane: ${lane}`);
    }
    queue.push(label);
    remaining += 1;
  }
  const order: string[] = [];
  let rounds = 0;
  while (remaining > 0) {
    rounds += 1;
    for (const [lane, quota] of plan) {
      const queue = queues.get(lane) as string[];
      for (let taken = 0; taken < quota && queue.length > 0; taken += 1) {
        order.push(queue.shift() as string);
        remaining -= 1;
      }
    }
  }
  return { order, rounds };
}
