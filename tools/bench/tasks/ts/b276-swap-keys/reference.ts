export function swapKeys(
  names: Record<string, string>,
): Record<string, string> {
  const swapped: Record<string, string> = {};
  for (const name of Object.keys(names).sort()) {
    const code = names[name];
    if (code !== "" && !(code in swapped)) {
      swapped[code] = name;
    }
  }
  return swapped;
}
