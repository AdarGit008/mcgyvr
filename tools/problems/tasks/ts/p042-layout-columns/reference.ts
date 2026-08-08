export function layoutColumns(rows: string[][], aligns: string): string[] {
  if (!Array.isArray(rows) || rows.length === 0) {
    throw new Error("empty table");
  }
  if (typeof aligns !== "string" || !/^[lrc]+$/.test(aligns)) {
    throw new Error("bad alignment spec");
  }
  for (const row of rows) {
    if (!Array.isArray(row) || row.length !== aligns.length) {
      throw new Error("row width does not match the spec");
    }
    for (const cell of row) {
      if (typeof cell !== "string") {
        throw new Error("cell is not a string");
      }
    }
  }
  const widths: number[] = [];
  for (let i = 0; i < aligns.length; i++) {
    widths.push(Math.max(...rows.map((row) => row[i].length)));
  }
  return rows.map((row) => {
    const parts = row.map((cell, i) => {
      const pad = widths[i] - cell.length;
      if (aligns[i] === "l") {
        return cell + " ".repeat(pad);
      }
      if (aligns[i] === "r") {
        return " ".repeat(pad) + cell;
      }
      const left = Math.floor(pad / 2);
      return " ".repeat(left) + cell + " ".repeat(pad - left);
    });
    return parts.join("  ").replace(/\s+$/, "");
  });
}
