from pathlib import Path
import solution

def check(cond, msg):
    if not cond:
        print("FAIL:", msg)
        raise SystemExit(1)

src = Path("solution.py").read_text()
check("import csv" not in src.replace("  ", " "),
      "contract forbids importing the csv module")

cases = [
    ("a,b,c", ["a", "b", "c"]),
    ('"a,b",c', ["a,b", "c"]),
    ('"say ""hi""",x', ['say "hi"', "x"]),
    ("a,,b", ["a", "", "b"]),
    ("", [""]),
    ('"",a', ["", "a"]),
]
for line, want in cases:
    got = solution.parse_csv_row(line)
    check(got == want, f"parse_csv_row({line!r}) = {got!r}, want {want!r}")
print("OK")
