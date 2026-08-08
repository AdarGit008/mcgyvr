function readPost(text: string): number[] {
  const parts = text.split(".");
  if (parts.length !== 3) {
    throw new Error("a post has exactly three numbers");
  }
  return parts.map((part) => {
    if (!/^\d{1,2}$/.test(part)) {
      throw new Error("not a number: " + part);
    }
    if (part.length === 2 && part[0] === "0") {
      throw new Error("number written with a padding zero");
    }
    const value = Number(part);
    if (value > 15) {
      throw new Error("number above 15");
    }
    return value;
  });
}

export function claimZone(claims: string[], where: string): string {
  if (!Array.isArray(claims)) {
    throw new Error("claims must be a list");
  }
  if (typeof where !== "string") {
    throw new Error("where must be a string");
  }
  const spot = readPost(where);
  const seen = new Set<string>();
  let bestDepth = -1;
  let bestName = "";
  for (const claim of claims) {
    if (typeof claim !== "string") {
      throw new Error("every claim must be a string");
    }
    const space = claim.indexOf(" ");
    if (space === -1) {
      throw new Error("claim carries no name");
    }
    const stencil = claim.slice(0, space);
    const name = claim.slice(space + 1);
    if (name === "" || name.includes(" ")) {
      throw new Error("name is empty or holds a space");
    }
    if (seen.has(stencil)) {
      throw new Error("two claims carry the same stencil");
    }
    seen.add(stencil);
    const slash = stencil.indexOf("/");
    if (slash === -1) {
      throw new Error("stencil carries no slash");
    }
    const fixed = readPost(stencil.slice(0, slash));
    const depthText = stencil.slice(slash + 1);
    if (!/^[0-3]$/.test(depthText)) {
      throw new Error("depth outside 0 to 3");
    }
    const depth = Number(depthText);
    for (let slot = depth; slot < 3; slot += 1) {
      if (fixed[slot] !== 0) {
        throw new Error("a number after the fixed ones is not 0");
      }
    }
    let covers = true;
    for (let slot = 0; slot < depth; slot += 1) {
      if (fixed[slot] !== spot[slot]) {
        covers = false;
      }
    }
    if (covers && depth > bestDepth) {
      bestDepth = depth;
      bestName = name;
    }
  }
  return bestName;
}
