export function expandRunTag(pattern: string): string[] {
  if (typeof pattern !== "string") {
    throw new Error("pattern must be a string");
  }
  const open = pattern.indexOf("[");
  const close = pattern.indexOf("]");
  if (open === -1 || close === -1) {
    throw new Error("no group");
  }
  if (close < open) {
    throw new Error("brackets reversed");
  }
  if (
    pattern.indexOf("[", open + 1) !== -1 ||
    pattern.indexOf("]", close + 1) !== -1
  ) {
    throw new Error("extra bracket");
  }
  const stem = pattern.slice(0, open);
  const tail = pattern.slice(close + 1);
  const body = pattern.slice(open + 1, close);
  if (body === "") {
    throw new Error("empty body");
  }
  let items: string[];
  const run = /^(\d+)-(\d+)(?:\/(\d+))?$/.exec(body);
  if (run !== null) {
    const lo = Number(run[1]);
    const hi = Number(run[2]);
    const step = run[3] === undefined ? 1 : Number(run[3]);
    if (lo > hi) {
      throw new Error("descending run");
    }
    if (step === 0) {
      throw new Error("zero step");
    }
    items = [];
    for (let v = lo; v <= hi; v += step) {
      items.push(String(v));
    }
  } else {
    items = body.split(",");
    for (const item of items) {
      if (item === "") {
        throw new Error("empty item");
      }
    }
  }
  const results = new Set(items.map((item) => stem + item + tail));
  return [...results].sort();
}
