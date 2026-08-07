export function foldReplyThread(messages: string[][]): string {
  if (!Array.isArray(messages) || messages.length === 0) {
    throw new Error("the batch must hold at least one message");
  }
  const texts = new Map<string, string>();
  for (const message of messages) {
    if (!Array.isArray(message) || message.length !== 3) {
      throw new Error("a message is exactly three values");
    }
    for (const field of message) {
      if (typeof field !== "string") {
        throw new Error("a message field must be a string");
      }
    }
    const [id, , text] = message;
    if (id.length === 0) {
      throw new Error("a message needs an id");
    }
    if (texts.has(id)) {
      throw new Error("two messages share an id");
    }
    if (text.includes("\n")) {
      throw new Error("a text may not carry a newline");
    }
    texts.set(id, text);
  }

  const openers: string[] = [];
  const answers = new Map<string, string[]>();
  for (const [id, parent] of messages) {
    if (parent.length === 0) {
      openers.push(id);
      continue;
    }
    if (!texts.has(parent)) {
      throw new Error("a parent names no message in the batch");
    }
    const kept = answers.get(parent);
    if (kept === undefined) {
      answers.set(parent, [id]);
    } else {
      kept.push(id);
    }
  }

  const lines: string[] = [];
  const walk = (id: string, depth: number): void => {
    lines.push("> ".repeat(depth) + id + " " + (texts.get(id) as string));
    for (const child of answers.get(id) ?? []) {
      walk(child, depth + 1);
    }
  };
  for (const id of openers) {
    walk(id, 0);
  }
  if (lines.length !== messages.length) {
    throw new Error("the parent links run in a circle");
  }
  return lines.join("\n");
}
