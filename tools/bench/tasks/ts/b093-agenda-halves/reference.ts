export function splitAgenda(sessions: number[][], limit: number): number[][] {
  if (!Number.isInteger(limit) || limit < 1) {
    throw new Error("limit must be a whole number of at least one minute");
  }
  const blocks: number[][] = [];
  const halve = (low: number, high: number): void => {
    if (high - low <= limit) {
      blocks.push([low, high]);
      return;
    }
    const mid = low + Math.ceil((high - low) / 2);
    halve(low, mid);
    halve(mid, high);
  };
  let previousEnd: number | null = null;
  for (const session of sessions) {
    const [start, end] = session;
    if (!Number.isInteger(start) || !Number.isInteger(end)) {
      throw new Error("session bounds must be whole minutes");
    }
    if (start >= end) {
      throw new Error("a session's start must precede its end");
    }
    if (previousEnd !== null && start < previousEnd) {
      throw new Error("sessions must be in order and must not overlap");
    }
    previousEnd = end;
    halve(start, end);
  }
  return blocks;
}
