/** Gather transcript lines into one block per stretch of a speaker. */

interface Block {
  speaker: string;
  text: string;
}

export function foldTranscript(lines: string[]): Block[] {
  const blocks: Block[] = [];
  for (const line of lines) {
    const mark = line.indexOf(":");
    if (mark < 0) {
      throw new Error("a transcript line needs a speaker and a colon");
    }
    const speaker = line.slice(0, mark).trim();
    const words = line.slice(mark + 1).trim();
    if (words === "") {
      continue;
    }
    const open = blocks[blocks.length - 1];
    if (open !== undefined && open.speaker === speaker) {
      open.text += " " + words;
    } else {
      blocks.push({ speaker, text: words });
    }
  }
  return blocks;
}
