export function holdQueue(callers: string[], limit: number): string[] {
  if (limit <= 0) {
    throw new Error("limit must be positive");
  }
  const waiting: string[] = [];
  for (const caller of callers) {
    waiting.push(caller);
    if (waiting.length > limit) {
      waiting.shift();
    }
  }
  return waiting;
}
