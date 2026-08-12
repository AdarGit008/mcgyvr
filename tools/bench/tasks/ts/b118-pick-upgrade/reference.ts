/** Firmware build selection within an installed release line. */

export function compareBuilds(a: string, b: string): number {
  const left = a.split(".").map(Number);
  const right = b.split(".").map(Number);
  const width = Math.max(left.length, right.length);
  for (let i = 0; i < width; i += 1) {
    const x = i < left.length ? left[i] : 0;
    const y = i < right.length ? right[i] : 0;
    if (x > y) {
      return 1;
    }
    if (x < y) {
      return -1;
    }
  }
  return 0;
}

const BUILD = /^(0|[1-9]\d*)(\.(0|[1-9]\d*))*$/;

function checkBuild(text: unknown): void {
  if (typeof text !== "string" || !BUILD.test(text)) {
    throw new Error("a build is dot-separated decimal numbers");
  }
}

export function pickUpgrade(installed: string, offers: string[]): string | null {
  checkBuild(installed);
  if (!Array.isArray(offers)) {
    throw new Error("offers must be a list");
  }
  const major = Number(installed.split(".")[0]);
  let best: string | null = null;
  for (const offer of offers) {
    checkBuild(offer);
    if (Number(offer.split(".")[0]) !== major) {
      continue;
    }
    if (compareBuilds(offer, installed) <= 0) {
      continue;
    }
    if (best === null || compareBuilds(offer, best) > 0) {
      best = offer;
    }
  }
  return best;
}
