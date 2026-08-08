export function collateFeeds(feeds: number[][][]): number[][] {
  const entries: number[][] = [];
  feeds.forEach((feed, index) => {
    let previous: number | null = null;
    for (const [tick, reading] of feed) {
      if (previous !== null && tick <= previous) {
        throw new Error(`feed ${index} ticks are not strictly increasing`);
      }
      previous = tick;
      entries.push([tick, index, reading]);
    }
  });
  entries.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  const timeline: number[][] = [];
  let lastTick: number | null = null;
  for (const [tick, , reading] of entries) {
    if (tick === lastTick) {
      continue;
    }
    lastTick = tick;
    if (timeline.length > 0 && timeline[timeline.length - 1][1] === reading) {
      continue;
    }
    timeline.push([tick, reading]);
  }
  return timeline;
}
