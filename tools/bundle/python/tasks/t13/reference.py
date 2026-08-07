def reverse_words(sentence: str) -> str:
    """Reverse the order of space-separated words."""
    return " ".join(sentence.split(" ")[::-1])
