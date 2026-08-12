"""Replay a notepad editing session: type, erase, replace, undo and redo."""


def replay_notepad(commands):
    def is_count(value):
        return not isinstance(value, bool) and isinstance(value, int) and value > 0

    buffer = ""
    past = []
    future = []
    for command in commands:
        if not isinstance(command, list) or len(command) < 2:
            raise ValueError("command must be an action and its payload")
        action = command[0]
        if action == "type":
            if len(command) != 2:
                raise ValueError("type takes exactly one text")
            text = command[1]
            if not isinstance(text, str) or not text:
                raise ValueError("type text must be a non-empty string")
            past.append(buffer)
            future = []
            buffer += text
        elif action == "erase":
            if len(command) != 2:
                raise ValueError("erase takes exactly one count")
            count = command[1]
            if not is_count(count):
                raise ValueError("erase count must be a positive integer")
            if count > len(buffer):
                raise ValueError("erase count exceeds the buffer")
            past.append(buffer)
            future = []
            buffer = buffer[: len(buffer) - count]
        elif action == "replace":
            if len(command) != 3:
                raise ValueError("replace takes an old and a new text")
            old, new = command[1], command[2]
            if not isinstance(old, str) or not old:
                raise ValueError("replace old text must be a non-empty string")
            if not isinstance(new, str):
                raise ValueError("replace new text must be a string")
            at = buffer.rfind(old)
            if at == -1:
                raise ValueError("replace old text does not occur in the buffer")
            past.append(buffer)
            future = []
            buffer = buffer[:at] + new + buffer[at + len(old):]
        elif action == "undo":
            if len(command) != 2:
                raise ValueError("undo takes exactly one count")
            count = command[1]
            if not is_count(count):
                raise ValueError("undo count must be a positive integer")
            if count > len(past):
                raise ValueError("undo count exceeds the edits available")
            for _ in range(count):
                future.append(buffer)
                buffer = past.pop()
        elif action == "redo":
            if len(command) != 2:
                raise ValueError("redo takes exactly one count")
            count = command[1]
            if not is_count(count):
                raise ValueError("redo count must be a positive integer")
            if count > len(future):
                raise ValueError("redo count exceeds the edits available")
            for _ in range(count):
                past.append(buffer)
                buffer = future.pop()
        else:
            raise ValueError("unknown action: " + str(action))
    return buffer
