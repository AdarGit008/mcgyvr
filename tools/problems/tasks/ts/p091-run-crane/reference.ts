export function runCrane(script: string[][]): string[] {
  const pile: string[] = [];
  const manifest: string[] = [];
  for (let index = 0; index < script.length; index++) {
    const [name, label] = script[index];
    if (name === "load") {
      pile.push(label);
    } else if (name === "ship") {
      if (pile.length === 0) {
        throw new Error(`move ${index}: pile is empty`);
      }
      manifest.push(pile.pop() as string);
    } else if (name === "bury") {
      if (pile.length === 0) {
        throw new Error(`move ${index}: pile is empty`);
      }
      pile.unshift(pile.pop() as string);
    } else if (name === "scrap") {
      if (pile.length === 0) {
        throw new Error(`move ${index}: pile is empty`);
      }
      pile.pop();
    } else {
      throw new Error(`move ${index}: unknown move ${name}`);
    }
  }
  return manifest;
}
