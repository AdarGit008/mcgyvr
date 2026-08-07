export function linkLedgerMarks(
  marks: string[],
  aliases: Record<string, string>,
): [string, string[]][] {
  for (const [retired, replacement] of Object.entries(aliases)) {
    if (retired === replacement) {
      throw new Error("alias table maps a code to itself");
    }
    if (Object.prototype.hasOwnProperty.call(aliases, replacement)) {
      throw new Error("alias replacement is itself retired");
    }
  }
  const groups = new Map<string, string[]>();
  for (const raw of marks) {
    if (typeof raw !== "string") {
      throw new Error("mark must be a string");
    }
    const m = /^([A-Za-z]{2,3})[-/ ](\d+)([A-Za-z])$/.exec(raw);
    if (m === null) {
      throw new Error("malformed ledger mark");
    }
    let house = m[1].toUpperCase();
    const serial = Number(m[2]);
    const check = m[3].toUpperCase();
    if (serial === 0) {
      throw new Error("serial value must be at least 1");
    }
    if (check !== String.fromCharCode(65 + (serial % 26))) {
      throw new Error("check letter does not match serial");
    }
    if (Object.prototype.hasOwnProperty.call(aliases, house)) {
      house = aliases[house];
    }
    const canonical = `${house}-${serial}-${check}`;
    if (!groups.has(canonical)) {
      groups.set(canonical, []);
    }
    groups.get(canonical)!.push(raw);
  }
  return [...groups.entries()].map(([canonical, raws]) => [canonical, raws]);
}
