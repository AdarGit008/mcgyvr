/** Compare a digest manifest against held file contents and report the drift. */

function digestOf(text: string): string {
  let h = 0;
  for (let i = 0; i < text.length; i += 1) {
    h = (h * 31 + text.charCodeAt(i)) % 65521;
  }
  return h.toString(16).padStart(4, "0");
}

export function scanManifest(
  manifest: string,
  files: Record<string, string>,
): { intact: string[]; altered: string[]; lost: string[]; strays: string[] } {
  if (typeof manifest !== "string") {
    throw new Error("the manifest must be a string");
  }
  for (const name of Object.keys(files)) {
    if (typeof files[name] !== "string") {
      throw new Error(`held content is not a string: ${name}`);
    }
  }
  const expected = new Map<string, string>();
  for (const line of manifest.split("\n")) {
    if (line.trim() === "") {
      continue;
    }
    const cut = line.indexOf(" ");
    if (cut < 0) {
      throw new Error(`manifest line has no space: ${line}`);
    }
    const digest = line.slice(0, cut);
    const name = line.slice(cut + 1);
    if (!/^[0-9a-f]{4}$/.test(digest)) {
      throw new Error(`malformed digest: ${digest}`);
    }
    if (name === "") {
      throw new Error("manifest line names no file");
    }
    if (expected.has(name)) {
      throw new Error(`file listed twice: ${name}`);
    }
    expected.set(name, digest);
  }
  const intact: string[] = [];
  const altered: string[] = [];
  const lost: string[] = [];
  const strays: string[] = [];
  for (const [name, digest] of expected) {
    if (!(name in files)) {
      lost.push(name);
    } else if (digestOf(files[name]) === digest) {
      intact.push(name);
    } else {
      altered.push(name);
    }
  }
  for (const name of Object.keys(files)) {
    if (!expected.has(name)) {
      strays.push(name);
    }
  }
  intact.sort();
  altered.sort();
  lost.sort();
  strays.sort();
  return { intact, altered, lost, strays };
}
