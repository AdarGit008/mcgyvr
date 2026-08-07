export function runLoom(
  program: (string | number)[][],
): { status: string; output: number[]; step?: number } {
  const stack: number[] = [];
  const output: number[] = [];
  for (let step = 0; step < program.length; step++) {
    const [op, arg] = program[step];
    if (op === "put") {
      stack.push(arg as number);
    } else if (op === "twin") {
      if (stack.length < 1) {
        return { status: "starved", output, step };
      }
      stack.push(stack[stack.length - 1]);
    } else if (op === "flip") {
      if (stack.length < 2) {
        return { status: "starved", output, step };
      }
      const first = stack.pop() as number;
      const second = stack.pop() as number;
      stack.push(first, second);
    } else if (op === "fuse") {
      if (stack.length < 2) {
        return { status: "starved", output, step };
      }
      stack.push((stack.pop() as number) + (stack.pop() as number));
    } else if (op === "scale") {
      if (stack.length < 2) {
        return { status: "starved", output, step };
      }
      stack.push((stack.pop() as number) * (stack.pop() as number));
    } else if (op === "weave") {
      if (stack.length < 1) {
        return { status: "starved", output, step };
      }
      output.push(stack.pop() as number);
    } else {
      return { status: "lost", output, step };
    }
  }
  return { status: "done", output };
}
