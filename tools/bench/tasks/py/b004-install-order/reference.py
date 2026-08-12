"""An installation order for packages under prerequisite pairs."""


def install_order(packages, requires):
    if len(set(packages)) != len(packages):
        raise ValueError("a package is listed twice")
    needs = {name: 0 for name in packages}
    enables = {name: [] for name in packages}
    for pkg, needed in requires:
        if pkg not in needs or needed not in needs:
            raise ValueError("a requirement names an unknown package")
        needs[pkg] += 1
        enables[needed].append(pkg)
    ready = sorted(name for name in packages if needs[name] == 0)
    order = []
    while ready:
        next_name = ready.pop(0)
        order.append(next_name)
        for follower in enables[next_name]:
            needs[follower] -= 1
            if needs[follower] == 0:
                ready.append(follower)
        ready.sort()
    if len(order) != len(packages):
        raise ValueError("the requirements form a cycle")
    return order
