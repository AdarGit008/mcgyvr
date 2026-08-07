type Knot = { value: number; left: Knot | null; right: Knot | null };

function graft(knot: Knot | null, value: number): Knot {
  if (knot === null) {
    return { value, left: null, right: null };
  }
  if (value < knot.value) {
    knot.left = graft(knot.left, value);
  } else if (value > knot.value) {
    knot.right = graft(knot.right, value);
  }
  return knot;
}

function excise(knot: Knot | null, value: number): Knot | null {
  if (knot === null) {
    throw new Error("cannot drop a value the index does not hold");
  }
  if (value < knot.value) {
    knot.left = excise(knot.left, value);
    return knot;
  }
  if (value > knot.value) {
    knot.right = excise(knot.right, value);
    return knot;
  }
  if (knot.left === null) {
    return knot.right;
  }
  if (knot.right === null) {
    return knot.left;
  }
  let highest = knot.left;
  while (highest.right !== null) {
    highest = highest.right;
  }
  knot.value = highest.value;
  knot.left = excise(knot.left, highest.value);
  return knot;
}

export function replayTreeOps(steps: string[]): number[] {
  if (!Array.isArray(steps)) {
    throw new Error("steps must be a list");
  }
  let root: Knot | null = null;
  for (const step of steps) {
    if (typeof step !== "string" || !/^(?:add|drop):-?\d+$/.test(step)) {
      throw new Error("every step must read add:<n> or drop:<n>");
    }
    const cut = step.indexOf(":");
    const value = Number(step.slice(cut + 1));
    if (step.slice(0, cut) === "add") {
      root = graft(root, value);
    } else {
      root = excise(root, value);
    }
  }
  const out: number[] = [];
  const stack: Knot[] = root === null ? [] : [root];
  while (stack.length > 0) {
    const knot = stack.pop();
    out.push(knot.value);
    if (knot.right !== null) {
      stack.push(knot.right);
    }
    if (knot.left !== null) {
      stack.push(knot.left);
    }
  }
  return out;
}
