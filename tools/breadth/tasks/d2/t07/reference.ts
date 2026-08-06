/** Index of the first offending bracket, or -1 when balanced. */
export function firstUnbalanced(input: string): number {
  const partner: Record<string, string> = { ")": "(", "]": "[", "}": "{" };
  const openerIndices: number[] = [];
  for (let i = 0; i < input.length; i++) {
    const ch = input[i];
    if (ch === "(" || ch === "[" || ch === "{") {
      openerIndices.push(i);
    } else if (ch === ")" || ch === "]" || ch === "}") {
      const top = openerIndices[openerIndices.length - 1];
      if (top === undefined || input[top] !== partner[ch]) {
        return i;
      }
      openerIndices.pop();
    }
  }
  return openerIndices.length > 0 ? openerIndices[0] : -1;
}
