const CHANNEL_RANK: Record<string, number> = { dev: 0, alpha: 1, beta: 2, rc: 3 };

function parseRelease(text: string): [number, number, number, number] {
  if (typeof text !== "string") {
    throw new Error("release must be a string");
  }
  const match = /^(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-(dev|alpha|beta|rc)\.(\d+))?$/.exec(
    text,
  );
  if (match === null) {
    throw new Error("malformed release string");
  }
  if (match[3] === undefined) {
    return [Number(match[1]), Number(match[2]), 4, 0];
  }
  return [
    Number(match[1]),
    Number(match[2]),
    CHANNEL_RANK[match[3]],
    Number(match[4]),
  ];
}

export function newerRelease(a: string, b: string): number {
  const x = parseRelease(a);
  const y = parseRelease(b);
  for (let i = 0; i < 4; i++) {
    if (x[i] !== y[i]) {
      return x[i] > y[i] ? 1 : -1;
    }
  }
  return 0;
}
