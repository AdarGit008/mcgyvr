/** Count the directory steps between two paths under one shared root. */
function reduceSegments(path: string): string[] {
  const stack: string[] = [];
  for (const piece of path.split("/")) {
    if (piece === "" || piece === ".") {
      continue;
    }
    if (piece === "..") {
      if (stack.length === 0) {
        throw new Error(`path climbs above the root: ${path}`);
      }
      stack.pop();
    } else {
      stack.push(piece);
    }
  }
  return stack;
}

export function pathHops(start: string, goal: string): number {
  const here = reduceSegments(start);
  const there = reduceSegments(goal);
  let shared = 0;
  while (shared < here.length && shared < there.length && here[shared] === there[shared]) {
    shared += 1;
  }
  return here.length - shared + (there.length - shared);
}
