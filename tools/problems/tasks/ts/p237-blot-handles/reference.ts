const HANDLE = /(?<![a-z0-9_@])@[a-z0-9_]{3,12}(?![a-z0-9_])/g;

function blotPlain(part: string): string {
  return part.replace(
    HANDLE,
    (found) => "@" + found[1] + ".".repeat(found.length - 2),
  );
}

export function blotHandles(message: string): string {
  if (typeof message !== "string") {
    throw new Error("blotHandles expects a string");
  }
  const parts: string[] = [];
  let index = 0;
  while (index < message.length) {
    const open = message.indexOf("`", index);
    if (open < 0) {
      parts.push(blotPlain(message.slice(index)));
      break;
    }
    parts.push(blotPlain(message.slice(index, open)));
    const shut = message.indexOf("`", open + 1);
    if (shut < 0) {
      parts.push(message.slice(open));
      break;
    }
    parts.push(message.slice(open, shut + 1));
    index = shut + 1;
  }
  return parts.join("");
}
