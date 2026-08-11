def trace_relay(links, start):
    if not isinstance(links, dict): raise ValueError("links must be a mapping")
    if start not in links: raise ValueError("start is not a post")
    route = []
    post = start
    while post != "":
        if post in route: raise ValueError("the watch comes back on itself")
        if post not in links: raise ValueError("a handoff names a post links does not hold")
        route.append(post)
        post = links[post]
    return route
