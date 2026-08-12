/** Cut a chunked stream into frames at a marker, doubled to escape it. */
export function drainFrames(chunks: string[], marker: string): { frames: string[]; pending: string } {
  if (typeof marker !== "string" || marker.length !== 1) {
    throw new Error("marker must be a single character");
  }
  const buffer = chunks.join("");
  const frames: string[] = [];
  let held = "";
  let at = 0;
  while (at < buffer.length) {
    if (buffer[at] !== marker) {
      held += buffer[at];
      at += 1;
    } else if (buffer[at + 1] === marker) {
      held += marker;
      at += 2;
    } else if (at + 1 === buffer.length) {
      held += marker;
      at += 1;
    } else {
      frames.push(held);
      held = "";
      at += 1;
    }
  }
  return { frames, pending: held };
}
