def toggle_run(steps: list) -> bool:
    state = False
    for step in steps:
        if step == "on":
            state = True
        elif step == "off":
            state = False
        elif step == "flip":
            state = not state
    return state
