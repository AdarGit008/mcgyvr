type Tree = { [key: string]: string | Tree };
const isTree = (v: unknown): v is Tree =>
  typeof v === "object" && v !== null && !Array.isArray(v);

export function diffPaths(before: Tree, after: Tree): string[] {
  if (!isTree(before) || !isTree(after)) throw new Error("both arguments must be mappings");
  const paths: string[] = [];
  for (const key of new Set([...Object.keys(before), ...Object.keys(after)])) {
    const va = before[key];
    const vb = after[key];
    for (const v of [va, vb]) {
      if (v !== undefined && typeof v !== "string" && !isTree(v)) throw new Error("every value must be a string or a mapping");
    }
    if (isTree(va) && isTree(vb)) paths.push(...diffPaths(va, vb).map((p) => key + "/" + p));
    else if (va !== vb) paths.push(key);
  }
  return paths.sort();
}
