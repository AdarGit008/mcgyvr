export function leafPaths(rows: [string, string][]): string[] {
  if (rows.length === 0) {
    throw new Error("the hierarchy is empty");
  }
  const parent = new Map<string, string>();
  for (const [id, up] of rows) {
    if (parent.has(id)) {
      throw new Error(`duplicated id ${id}`);
    }
    parent.set(id, up);
  }
  const roots: string[] = [];
  const children = new Map<string, string[]>();
  for (const [id, up] of rows) {
    if (up === "") {
      roots.push(id);
    } else if (!parent.has(up)) {
      throw new Error(`unknown parent ${up}`);
    } else {
      const kids = children.get(up) ?? [];
      kids.push(id);
      children.set(up, kids);
    }
  }
  if (roots.length !== 1) {
    throw new Error("the hierarchy needs exactly one root");
  }
  const paths: string[] = [];
  let visited = 0;
  const walk = (id: string, prefix: string): void => {
    visited += 1;
    const here = prefix === "" ? id : `${prefix}/${id}`;
    const kids = children.get(id) ?? [];
    if (kids.length === 0) {
      paths.push(here);
      return;
    }
    for (const kid of kids) {
      walk(kid, here);
    }
  };
  walk(roots[0], "");
  if (visited !== rows.length) {
    throw new Error("some rows cannot be reached from the root");
  }
  paths.sort();
  return paths;
}
