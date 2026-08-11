export function bumpRelease(version: string, part: string): string {
  if (typeof version !== "string") {
    throw new Error("version must be a string");
  }
  const pieces = version.split(".");
  if (pieces.length !== 3) {
    throw new Error("version must have exactly three components");
  }
  const numbers = pieces.map((piece) => {
    if (!/^(0|[1-9]\d*)$/.test(piece)) {
      throw new Error("bad version component: " + piece);
    }
    return Number(piece);
  });
  const [major, minor, patch] = numbers;
  if (part === "major") {
    return `${major + 1}.0.0`;
  }
  if (part === "minor") {
    return `${major}.${minor + 1}.0`;
  }
  if (part === "patch") {
    return `${major}.${minor}.${patch + 1}`;
  }
  throw new Error("unknown part: " + part);
}
