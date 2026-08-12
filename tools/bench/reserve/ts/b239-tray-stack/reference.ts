export function trayPush(stack: string[], item: string): string[] {
  return [...stack, item];
}

export function trayTop(stack: string[]): string | null {
  return stack.length === 0 ? null : stack[stack.length - 1];
}
