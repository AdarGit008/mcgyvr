import typing
import solution

def check(cond, msg):
    if not cond:
        print("FAIL:", msg)
        raise SystemExit(1)

th = typing.get_type_hints(solution.find_user)
check(th.get("users") == list[dict[str, int]],
      f"users annotation is {th.get('users')}, want list[dict[str, int]]")
check(th.get("user_id") is int, f"user_id annotation is {th.get('user_id')}, want int")
ret = th.get("return")
want_ret = typing.Optional[dict[str, int]]
check(ret == want_ret, f"return annotation is {ret}, want {want_ret}")

users = [{"id": 1, "age": 30}, {"id": 2, "age": 40}]
check(solution.find_user(users, 2) == {"id": 2, "age": 40}, "lookup broken")
check(solution.find_user(users, 99) is None, "missing id should return None")
check(solution.find_user([], 1) is None, "empty list should return None")
print("OK")
