from solution import chart_depths


def rejects(chart):
    try:
        chart_depths(chart)
    except Exception:
        return True
    return False


assert chart_depths({"vera": ""}) == {"vera": 0}, "the chief sits on rung zero"
assert chart_depths({"vera": "", "omar": "vera"}) == {"vera": 0, "omar": 1}, "a direct report sits one above"
assert chart_depths({"ines": "omar", "omar": "vera", "vera": ""}) == {
    "ines": 2,
    "omar": 1,
    "vera": 0,
}, "a chain listed upside down still measures"
assert chart_depths({"vera": "", "omar": "vera", "ines": "vera", "kip": "ines", "lena": "kip"}) == {
    "vera": 0,
    "omar": 1,
    "ines": 1,
    "kip": 2,
    "lena": 3,
}, "separate branches keep their own rungs"
assert chart_depths({}) == {}, "an empty chart has no rungs"
assert rejects({"omar": "ghost"}), "answering to an unlisted member is rejected"
assert rejects({"omar": "ines", "ines": "omar"}), "a chart that circles back is rejected"
print("ok")
