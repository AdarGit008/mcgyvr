import solution

def check(cond, msg):
    if not cond:
        print("FAIL:", msg)
        raise SystemExit(1)

text = """
# comment
HOST = example.com
PORT=8080

  # indented comment
URL = https://x.io/?a=1&b=2
EMPTY=
HOST = override.com
"""
got = solution.read_config(text)
want = {"HOST": "override.com", "PORT": "8080",
        "URL": "https://x.io/?a=1&b=2", "EMPTY": ""}
check(got == want, f"read_config = {got}, want {want}")
check(solution.read_config("") == {}, "empty text -> {}")
check(solution.read_config("\n\n# only comments\n") == {}, "comments only -> {}")

for bad in ["JUSTAWORD", "A=1\nBROKEN LINE\n", "=value", "  =x"]:
    try:
        got = solution.read_config(bad)
    except ValueError:
        continue
    print(f"FAIL: read_config({bad!r}) should raise ValueError, got {got!r}")
    raise SystemExit(1)
print("OK")
