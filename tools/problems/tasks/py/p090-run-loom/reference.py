def run_loom(program):
    stack = []
    output = []
    for step, instruction in enumerate(program):
        op = instruction[0]
        if op == "put":
            stack.append(instruction[1])
        elif op == "twin":
            if not stack:
                return {"status": "starved", "output": output, "step": step}
            stack.append(stack[-1])
        elif op == "flip":
            if len(stack) < 2:
                return {"status": "starved", "output": output, "step": step}
            stack[-1], stack[-2] = stack[-2], stack[-1]
        elif op == "fuse":
            if len(stack) < 2:
                return {"status": "starved", "output": output, "step": step}
            stack.append(stack.pop() + stack.pop())
        elif op == "scale":
            if len(stack) < 2:
                return {"status": "starved", "output": output, "step": step}
            stack.append(stack.pop() * stack.pop())
        elif op == "weave":
            if not stack:
                return {"status": "starved", "output": output, "step": step}
            output.append(stack.pop())
        else:
            return {"status": "lost", "output": output, "step": step}
    return {"status": "done", "output": output}
