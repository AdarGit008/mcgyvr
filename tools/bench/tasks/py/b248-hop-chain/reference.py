def hop_chain(hops: list) -> bool:
    for i in range(1, len(hops)):
        if hops[i - 1][1] != hops[i][0]:
            return False
    return True
