"""Gather transcript lines into one block per stretch of a speaker."""


def fold_transcript(lines: list[str]) -> list[dict]:
    blocks: list[dict] = []
    for line in lines:
        mark = line.find(":")
        if mark < 0:
            raise ValueError("a transcript line needs a speaker and a colon")
        speaker = line[:mark].strip()
        words = line[mark + 1 :].strip()
        if words == "":
            continue
        if blocks and blocks[-1]["speaker"] == speaker:
            blocks[-1]["text"] += " " + words
        else:
            blocks.append({"speaker": speaker, "text": words})
    return blocks
