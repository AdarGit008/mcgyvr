def money_text(pence: int) -> str:
    pounds = pence // 100
    rest = pence - pounds * 100
    shown = "0" + str(rest) if rest < 10 else str(rest)
    return str(pounds) + "." + shown
