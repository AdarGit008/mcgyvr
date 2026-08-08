const ITEM = /^(\d+)(?:([-+])(\d+))?$/;
const LAST_PAGE = 9999;

function figure(text: string): number {
  if (text.length > 1 && text.startsWith("0")) {
    throw new Error(`the figure ${text} carries a leading nought`);
  }
  return Number(text);
}

export function countLeafletPicks(picks: string): number {
  if (typeof picks !== "string") {
    throw new Error("a pick list must be a string");
  }
  if (picks.length === 0) {
    throw new Error("a pick list may not be empty");
  }
  if (!/^[0-9,+-]+$/.test(picks)) {
    throw new Error("a pick list holds only digits, commas, hyphens and plus signs");
  }

  const pages = new Set<number>();
  for (const item of picks.split(",")) {
    if (item.length === 0) {
      throw new Error("a pick list may not hold an empty item");
    }
    const parts = ITEM.exec(item);
    if (parts === null) {
      throw new Error(`the item ${item} matches none of the three shapes`);
    }
    const first = figure(parts[1]);
    if (first < 1 || first > LAST_PAGE) {
      throw new Error(`the page ${first} falls outside 1 through ${LAST_PAGE}`);
    }
    if (parts[2] === undefined) {
      pages.add(first);
      continue;
    }
    const second = figure(parts[3]);
    let last: number;
    if (parts[2] === "-") {
      if (second < first) {
        throw new Error("a hyphen item may not run backwards");
      }
      last = second;
    } else {
      if (second < 1) {
        throw new Error("a plus item must carry at least one page behind it");
      }
      last = first + second;
    }
    if (last > LAST_PAGE) {
      throw new Error(`the page ${last} falls outside 1 through ${LAST_PAGE}`);
    }
    for (let page = first; page <= last; page++) {
      pages.add(page);
    }
  }
  return pages.size;
}
