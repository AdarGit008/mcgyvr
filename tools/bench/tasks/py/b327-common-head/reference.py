def common_head(words: list) -> str:
    if not words:
        return ""
    head = words[0]
    for word in words[1:]:
        while not word.startswith(head):
            head = head[:-1]
    return head
