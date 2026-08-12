export function forkPaths(pattern: string): string[] {
  if (typeof pattern !== "string" || pattern === "") throw new Error("pattern must be a non-empty string");
  const expand = (segs: string[]): string[][] => {
    if (segs.length === 0) return [[]];
    const found = /^\{([^{}]+)\}$/.exec(segs[0]);
    const options = found ? found[1].split(",") : [segs[0]];
    for (const option of options) {
      if (option === "" || /[{},]/.test(option)) throw new Error("malformed segment");
    }
    const tails = expand(segs.slice(1));
    return options.flatMap((option) => tails.map((tail) => [option, ...tail]));
  };
  return expand(pattern.split("/")).map((parts) => parts.join("/"));
}
