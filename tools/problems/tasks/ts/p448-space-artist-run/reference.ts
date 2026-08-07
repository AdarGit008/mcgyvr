export function spaceArtistRun(tracks: Record<string, string>[]): string[] {
  if (!Array.isArray(tracks) || tracks.length === 0) {
    throw new Error("there must be at least one track");
  }

  const queues = new Map<string, string[]>();
  const earliest = new Map<string, number>();
  const seen = new Set<string>();

  for (let index = 0; index < tracks.length; index++) {
    const track = tracks[index];
    const title = track.title;
    const artist = track.artist;
    if (typeof title !== "string" || title.length === 0) {
      throw new Error("every track needs a title");
    }
    if (typeof artist !== "string" || artist.length === 0) {
      throw new Error(`the track ${title} needs an artist`);
    }
    if (seen.has(title)) {
      throw new Error(`the title ${title} appears twice`);
    }
    seen.add(title);
    if (!queues.has(artist)) {
      queues.set(artist, []);
      earliest.set(artist, index);
    }
    (queues.get(artist) as string[]).push(title);
  }

  const run: string[] = [];
  let previous = "";
  for (let place = 0; place < tracks.length; place++) {
    let choice = "";
    let bestLeft = 0;
    let bestAt = 0;
    for (const [artist, queue] of queues) {
      if (queue.length === 0 || artist === previous) {
        continue;
      }
      const at = earliest.get(artist) as number;
      if (
        choice === "" ||
        queue.length > bestLeft ||
        (queue.length === bestLeft && at < bestAt)
      ) {
        choice = artist;
        bestLeft = queue.length;
        bestAt = at;
      }
    }
    if (choice === "") {
      throw new Error("no order can keep every artist apart");
    }
    const queue = queues.get(choice) as string[];
    run.push(queue.shift() as string);
    previous = choice;
  }
  return run;
}
