function whole(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

export function foldSignatureMap(
  pages: number,
  perSignature: number,
  wanted: number[],
): string[] {
  if (!whole(pages) || pages < 1 || pages > 20000) {
    throw new Error("the pages are not whole or fall outside one through twenty thousand");
  }
  if (!whole(perSignature) || perSignature < 4 || perSignature > 400) {
    throw new Error("the perSignature is not whole or falls outside four through four hundred");
  }
  if (perSignature % 4 !== 0) {
    throw new Error("the perSignature does not divide by four");
  }
  if (!Array.isArray(wanted)) {
    throw new Error("the wanted pages are not a list");
  }
  for (const page of wanted) {
    if (!whole(page) || page < 1 || page > pages) {
      throw new Error("a wanted page is not whole or falls outside one through the page count");
    }
  }

  const half = perSignature / 2;
  const lines: string[] = [];
  for (const page of wanted) {
    const signature = Math.floor((page - 1) / perSignature) + 1;
    const place = page - (signature - 1) * perSignature;
    let sheet = 0;
    let side = "front";
    let edge = "right";
    if (place % 2 === 1) {
      if (place <= half) {
        sheet = (place + 1) / 2;
        side = "front";
        edge = "right";
      } else {
        sheet = (perSignature + 1 - place) / 2;
        side = "back";
        edge = "right";
      }
    } else if (place <= half) {
      sheet = place / 2;
      side = "back";
      edge = "left";
    } else {
      sheet = (perSignature + 2 - place) / 2;
      side = "front";
      edge = "left";
    }
    lines.push(`${page} ${signature} ${sheet} ${side} ${edge}`);
  }
  return lines;
}
