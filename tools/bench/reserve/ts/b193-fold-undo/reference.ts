type Change = [string, string, string];

/** Fold a stream of field edits into a bounded, merged undo stack. */
export function foldUndo(changes: Change[], depth: number): Change[] {
  const stack: Change[] = [];
  for (const [field, before, after] of changes) {
    const top = stack[stack.length - 1];
    let entry: Change;
    if (top !== undefined && top[0] === field) {
      stack.pop();
      entry = [field, top[1], after];
    } else {
      entry = [field, before, after];
    }
    if (entry[1] === entry[2]) {
      continue;
    }
    stack.push(entry);
    if (stack.length > depth) {
      stack.shift();
    }
  }
  return stack;
}
