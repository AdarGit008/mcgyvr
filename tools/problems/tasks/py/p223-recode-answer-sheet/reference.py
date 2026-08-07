import re


def _fragment_list(raw) -> list:
    if not isinstance(raw, list):
        raise ValueError("a fragment list must be a list")
    seen = set()
    for fragment in raw:
        if not isinstance(fragment, str) or not fragment:
            raise ValueError("a fragment must be a non-empty string")
        if fragment.lower() != fragment:
            raise ValueError("a fragment must carry no capital letter")
        if fragment in seen:
            raise ValueError("a fragment list repeats a fragment")
        seen.add(fragment)
    return raw


def _whole(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def recode_answer_sheet(sheet: dict) -> dict:
    if not isinstance(sheet, dict):
        raise ValueError("the sheet must be a mapping")
    steps = sheet.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ValueError("the steps must be a non-empty list")
    labels = []
    wanted = []
    barred = []
    least = []
    seen_label = set()
    for step in steps:
        if not isinstance(step, dict):
            raise ValueError("a step must be a mapping")
        label = step.get("label")
        if not isinstance(label, str) or not label:
            raise ValueError("a label must be a non-empty string")
        if label in seen_label:
            raise ValueError("two steps share a label")
        seen_label.add(label)
        want = _fragment_list(step.get("wanted"))
        if not want:
            raise ValueError("a step must want at least one fragment")
        bar = _fragment_list(step.get("barred"))
        floor = step.get("least")
        if not _whole(floor) or floor < 1 or floor > len(want):
            raise ValueError("least must be a whole number within the wanted list")
        labels.append(label)
        wanted.append(want)
        barred.append(bar)
        least.append(floor)
    entries = sheet.get("entries")
    if not isinstance(entries, list):
        raise ValueError("the entries must be a list")
    coded = []
    loose = []
    used = set()
    seen_id = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("an entry must be a mapping")
        entry_id = entry.get("id")
        text = entry.get("text")
        if not isinstance(entry_id, str) or not entry_id:
            raise ValueError("an id must be a non-empty string")
        if entry_id in seen_id:
            raise ValueError("two entries share an id")
        seen_id.add(entry_id)
        if not isinstance(text, str):
            raise ValueError("an entry's text must be a string")
        folded = re.sub(r"\s+", " ", text.lower()).strip()
        chosen = ""
        for at, label in enumerate(labels):
            if any(fragment in folded for fragment in barred[at]):
                continue
            hits = sum(1 for fragment in wanted[at] if fragment in folded)
            if hits >= least[at]:
                chosen = label
                break
        if chosen == "":
            loose.append(entry_id)
        else:
            coded.append({"id": entry_id, "label": chosen})
            used.add(chosen)
    return {
        "coded": coded,
        "loose": loose,
        "unused": [label for label in labels if label not in used],
    }
