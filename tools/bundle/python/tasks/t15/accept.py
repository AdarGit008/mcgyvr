import solution

def check(cond, msg):
    if not cond:
        print("FAIL:", msg)
        raise SystemExit(1)

vals = [0.0, 100.0, -40.0, 36.6]
want_f = [32, 212, -40, 98]
want_k = [273, 373, 233, 310]

check(solution.convert_temps(vals, "fahrenheit") == want_f,
      f"convert_temps fahrenheit wrong: {solution.convert_temps(vals, 'fahrenheit')}")
check(solution.convert_temps(vals, "kelvin") == want_k,
      f"convert_temps kelvin wrong: {solution.convert_temps(vals, 'kelvin')}")
check(solution.celsius_to_fahrenheit_rounded(vals) == want_f,
      "celsius_to_fahrenheit_rounded wrapper broken")
check(solution.celsius_to_kelvin_rounded(vals) == want_k,
      "celsius_to_kelvin_rounded wrapper broken")
check(solution.convert_temps([], "kelvin") == [], "empty input -> []")

try:
    solution.convert_temps([1.0], "rankine")
    print("FAIL: unknown mode should raise ValueError")
    raise SystemExit(1)
except ValueError:
    pass
print("OK")
