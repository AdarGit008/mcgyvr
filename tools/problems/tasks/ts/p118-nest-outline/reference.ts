export function nestOutline(text: string): any[] {
  if (typeof text !== "string" || text === "") {
    throw new Error("input must be a non-empty string");
  }
  if (text.includes("\t")) {
    throw new Error("tabs are not allowed");
  }
  const lines = text.split("\n");
  if (lines.length > 1 && lines[lines.length - 1] === "") {
    lines.pop();
  }
  const roots: any[] = [];
  const stack: any[] = [];
  let previousDepth = -1;
  for (const line of lines) {
    const body = line.replace(/^ */, "");
    if (body === "") {
      throw new Error("blank lines are not allowed");
    }
    const indent = line.length - body.length;
    if (indent % 2 !== 0) {
      throw new Error("indentation must be a multiple of two spaces");
    }
    const depth = indent / 2;
    if (depth > previousDepth + 1) {
      throw new Error("a line may nest at most one level deeper");
    }
    const node: any[] = [body, []];
    stack.length = depth;
    if (depth === 0) {
      roots.push(node);
    } else {
      stack[depth - 1][1].push(node);
    }
    stack.push(node);
    previousDepth = depth;
  }
  return roots;
}
