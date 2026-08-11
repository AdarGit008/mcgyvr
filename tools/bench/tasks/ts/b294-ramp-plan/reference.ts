export function rampStep(
  current: number,
  target: number,
  step: number,
): number {
  if (current < target) {
    return Math.min(current + step, target);
  }
  if (current > target) {
    return Math.max(current - step, target);
  }
  return current;
}

export function rampPlan(
  start: number,
  target: number,
  step: number,
): number[] {
  const visited = [start];
  while (visited[visited.length - 1] !== target) {
    visited.push(rampStep(visited[visited.length - 1], target, step));
  }
  return visited;
}
