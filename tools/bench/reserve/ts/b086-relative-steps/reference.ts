export function splitAbsolute(path: string): string[] {
  if (typeof path !== "string" || path[0] !== "/") {
    throw new Error("expected an absolute path");
  }
  if (path === "/") {
    return [];
  }
  const segments = path.slice(1).split("/");
  for (const segment of segments) {
    if (segment === "" || segment === "." || segment === "..") {
      throw new Error("bad segment: " + segment);
    }
  }
  return segments;
}

export function relativeSteps(fromDir: string, toPath: string): string {
  const origin = splitAbsolute(fromDir);
  const goal = splitAbsolute(toPath);
  let shared = 0;
  while (shared < origin.length && shared < goal.length) {
    if (origin[shared] !== goal[shared]) {
      break;
    }
    shared++;
  }
  const steps: string[] = [];
  for (let i = shared; i < origin.length; i++) {
    steps.push("..");
  }
  for (let i = shared; i < goal.length; i++) {
    steps.push(goal[i]);
  }
  return steps.length === 0 ? "." : steps.join("/");
}
