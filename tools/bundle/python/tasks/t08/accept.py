import solution

def check(cond, msg):
    if not cond:
        print("FAIL:", msg)
        raise SystemExit(1)

def verify(n, edges):
    order = solution.topo_sort(n, edges)
    check(sorted(order) == list(range(n)),
          f"topo_sort({n}, {edges}) = {order} is not a permutation of 0..{n-1}")
    pos = {v: i for i, v in enumerate(order)}
    for a, b in edges:
        check(pos[a] < pos[b], f"edge ({a},{b}) violated in {order}")

verify(4, [(0, 1), (0, 2), (1, 3), (2, 3)])
verify(3, [])
verify(0, [])
verify(6, [(5, 0), (5, 2), (4, 0), (4, 1), (2, 3), (3, 1)])
verify(2, [(1, 0)])

for n, edges in [(2, [(0, 1), (1, 0)]), (3, [(0, 1), (1, 2), (2, 0)]),
                 (1, [(0, 0)])]:
    try:
        got = solution.topo_sort(n, edges)
    except ValueError:
        continue
    print(f"FAIL: topo_sort({n}, {edges}) should raise ValueError (cycle), got {got}")
    raise SystemExit(1)
print("OK")
