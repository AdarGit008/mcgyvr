import typing
import solution

def check(cond, msg):
    if not cond:
        print("FAIL:", msg)
        raise SystemExit(1)

th = typing.get_type_hints(solution.greet)
check(th.get("name") is str, f"greet name annotation is {th.get('name')}, want str")
check(th.get("greeting") is str, f"greet greeting annotation is {th.get('greeting')}, want str")
check(th.get("return") is str, f"greet return annotation is {th.get('return')}, want str")

th2 = typing.get_type_hints(solution.total_length)
check(th2.get("strings") == list[str],
      f"total_length strings annotation is {th2.get('strings')}, want list[str]")
check(th2.get("return") is int, f"total_length return is {th2.get('return')}, want int")

check(solution.greet("Ada") == "Hello, Ada!", "greet behavior changed")
check(solution.greet("Ada", "Hi") == "Hi, Ada!", "greet custom greeting broken")
check(solution.total_length(["ab", "cde"]) == 5, "total_length behavior changed")
check(solution.total_length([]) == 0, "total_length([]) should be 0")
print("OK")
