/** Order release tags by version, previews ahead of their plain release. */
function tagKey(tag: string): (number | string)[] {
  const dash = tag.indexOf("-");
  const core = dash === -1 ? tag.slice(1) : tag.slice(1, dash);
  const parts = core.split(".").map(Number);
  if (dash === -1) {
    return [parts[0], parts[1], parts[2], 1, "", 0];
  }
  const preview = tag.slice(dash + 1);
  const cut = preview.search(/\d/);
  const word = preview.slice(0, cut);
  return [parts[0], parts[1], parts[2], 0, word, Number(preview.slice(cut))];
}

export function orderReleaseTags(tags: string[]): string[] {
  return tags.slice().sort((left, right) => {
    const first = tagKey(left);
    const second = tagKey(right);
    for (let slot = 0; slot < first.length; slot += 1) {
      if (first[slot] < second[slot]) {
        return -1;
      }
      if (first[slot] > second[slot]) {
        return 1;
      }
    }
    return 0;
  });
}
