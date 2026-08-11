/** Report the first fault in a viewer filter mask, or "ok" when it is sound. */
export function maskFault(mask: string): string {
  let members: [string, number][] = [];
  let openAt = -1;
  for (let i = 0; i < mask.length; i++) {
    const at = i;
    let ch = mask[i];
    if (ch === "\\" && i + 1 === mask.length) return `dangling escape at ${at}`;
    if (ch === "\\") ch = "\\" + mask[++i];
    if (openAt < 0) {
      if (ch === "[") {
        openAt = at;
        members = [];
      }
    } else if (ch === "]") {
      for (let k = 1; k + 1 < members.length; k++) {
        if (members[k][0] !== "-") continue;
        const from = members[k - 1][0].slice(-1);
        const to = members[k + 1][0].slice(-1);
        if (to < from) return `reversed range at ${members[k - 1][1]}`;
      }
      openAt = -1;
    } else {
      members.push([ch, at]);
    }
  }
  return openAt >= 0 ? `unclosed class at ${openAt}` : "ok";
}
