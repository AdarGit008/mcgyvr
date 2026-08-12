export function netTally(sheets: string[]): string {
  if (!Array.isArray(sheets)) {
    throw new Error("sheets must be a list");
  }
  const sold = new Map<string, number>();
  const returned = new Map<string, number>();
  for (const sheet of sheets) {
    if (typeof sheet !== "string") {
      throw new Error("every sheet must be a string");
    }
    for (const raw of sheet.split("\n")) {
      if (raw.trim() === "") {
        continue;
      }
      const fields = raw.split("|").map((field) => field.trim());
      if (fields.length !== 3) {
        throw new Error("a row is item|sold|returned");
      }
      const [item, soldText, returnedText] = fields;
      if (item === "") {
        throw new Error("item names must be non-empty");
      }
      if (!/^[0-9]+$/.test(soldText) || !/^[0-9]+$/.test(returnedText)) {
        throw new Error("counts must be strings of decimal digits");
      }
      sold.set(item, (sold.get(item) ?? 0) + Number(soldText));
      returned.set(item, (returned.get(item) ?? 0) + Number(returnedText));
    }
  }
  const items = [...sold.keys()].sort();
  let width = "total".length;
  for (const item of items) {
    width = Math.max(width, item.length);
  }
  const lines: string[] = [];
  let overall = 0;
  for (const item of items) {
    const net = (sold.get(item) ?? 0) - (returned.get(item) ?? 0);
    if (net < 0) {
      throw new Error("an item's returns exceed its sales");
    }
    overall += net;
    lines.push(item.padEnd(width) + "  " + String(net));
  }
  if (lines.length === 0) {
    return "";
  }
  lines.push("total".padEnd(width) + "  " + String(overall));
  return lines.join("\n");
}
