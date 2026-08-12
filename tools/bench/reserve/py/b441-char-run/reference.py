def char_run(text: str) -> int:
    best = 0
    run = 0
    for i in range(len(text)):
        run = run + 1 if i > 0 and text[i] == text[i - 1] else 1
        if run > best:
            best = run
    return best
