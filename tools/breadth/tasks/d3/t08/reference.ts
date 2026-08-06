/** Preorder codec: values in decimal, '#' for null, comma-separated. */
export type TreeNode = {
  value: number;
  left: TreeNode | null;
  right: TreeNode | null;
};

export function serialize(root: TreeNode | null): string {
  const parts: string[] = [];
  const walk = (node: TreeNode | null): void => {
    if (node === null) {
      parts.push("#");
      return;
    }
    parts.push(String(node.value));
    walk(node.left);
    walk(node.right);
  };
  walk(root);
  return parts.join(",");
}

export function deserialize(text: string): TreeNode | null {
  const parts = text.split(",");
  let pos = 0;
  const next = (): TreeNode | null => {
    if (pos >= parts.length) {
      throw new Error("input ended before the tree was complete");
    }
    const token = parts[pos];
    pos += 1;
    if (token === "#") return null;
    if (!/^-?\d+$/.test(token)) {
      throw new Error(`token ${JSON.stringify(token)} is not an integer or '#'`);
    }
    const value = Number(token);
    const left = next();
    const right = next();
    return { value, left, right };
  };
  const root = next();
  if (pos !== parts.length) {
    throw new Error("leftover tokens after the tree was complete");
  }
  return root;
}
