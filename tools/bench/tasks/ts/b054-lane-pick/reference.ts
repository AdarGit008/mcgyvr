export function pickLane(queues: number[], closed: number[]): number {
  if (!Array.isArray(queues) || queues.length === 0) {
    throw new Error("pickLane expects a non-empty list of queues");
  }
  for (const length of queues) {
    if (!Number.isInteger(length) || length < 0) {
      throw new Error("queue lengths must be non-negative integers");
    }
  }
  for (const index of closed) {
    if (!Number.isInteger(index) || index < 0 || index >= queues.length) {
      throw new Error("closed lane index out of range");
    }
  }
  let best = -1;
  for (let lane = 0; lane < queues.length; lane++) {
    if (closed.includes(lane)) {
      continue;
    }
    if (best === -1 || queues[lane] < queues[best]) {
      best = lane;
    }
  }
  if (best === -1) {
    throw new Error("every lane is closed");
  }
  return best;
}
