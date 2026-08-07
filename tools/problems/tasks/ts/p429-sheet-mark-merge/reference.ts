const SEGMENT = /^(!?)(\d+)(?:-(\d+))?$/;
const LAST_SHEET = 9999;

function figure(text: string): number {
  if (text.length > 1 && text.startsWith("0")) {
    throw new Error(`the figure ${text} carries a leading nought`);
  }
  const value = Number(text);
  if (value < 1 || value > LAST_SHEET) {
    throw new Error(`the sheet ${value} falls outside 1 through ${LAST_SHEET}`);
  }
  return value;
}

export function mergeSheetMarks(marks: string[]): { spec: string; sheets: number } {
  if (!Array.isArray(marks)) {
    throw new Error("the marks must be a list of strings");
  }
  const held = new Set<number>();
  for (const mark of marks) {
    if (typeof mark !== "string") {
      throw new Error("a mark must be a string");
    }
    if (mark.length === 0) {
      throw new Error("a mark may not be empty");
    }
    if (mark.startsWith(" ") || mark.endsWith(" ") || mark.includes("  ")) {
      throw new Error("segments are parted by exactly one blank apiece");
    }
    for (const segment of mark.split(" ")) {
      const parts = SEGMENT.exec(segment);
      if (parts === null) {
        throw new Error(`the segment ${segment} matches none of the four shapes`);
      }
      const first = figure(parts[2]);
      const last = parts[3] === undefined ? first : figure(parts[3]);
      if (last < first) {
        throw new Error("a hyphen segment may not run backwards");
      }
      for (let sheet = first; sheet <= last; sheet++) {
        if (parts[1] === "!") {
          held.delete(sheet);
        } else {
          held.add(sheet);
        }
      }
    }
  }

  const sorted = [...held].sort((a, b) => a - b);
  const runs: string[] = [];
  let index = 0;
  while (index < sorted.length) {
    let end = index;
    while (end + 1 < sorted.length && sorted[end + 1] === sorted[end] + 1) {
      end++;
    }
    runs.push(
      index === end ? String(sorted[index]) : `${sorted[index]}-${sorted[end]}`,
    );
    index = end + 1;
  }
  return { spec: runs.join(" "), sheets: sorted.length };
}
