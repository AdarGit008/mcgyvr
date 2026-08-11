"""Spread courses over numbered study terms, prerequisites strictly earlier."""


def plan_terms(courses: list, prereqs: list, per_term: int) -> list:
    if not isinstance(courses, list):
        raise ValueError("courses must be a list")
    known = set()
    for course in courses:
        if not isinstance(course, str) or not course:
            raise ValueError("each course must be a non-empty string")
        if course in known:
            raise ValueError(f"course listed twice: {course}")
        known.add(course)
    if isinstance(per_term, bool) or not isinstance(per_term, int) or per_term < 1:
        raise ValueError("per_term must be a whole number of at least one")
    if not isinstance(prereqs, list):
        raise ValueError("prereqs must be a list")
    needs = {course: [] for course in courses}
    for pair in prereqs:
        if not isinstance(pair, list) or len(pair) != 2:
            raise ValueError("each prereq must be a [course, needed] pair")
        course, needed = pair
        if course not in known or needed not in known:
            raise ValueError("prereq names a course absent from the list")
        needs[course].append(needed)
    planned = set()
    terms = []
    while len(planned) < len(known):
        ready = []
        for course in courses:
            if course in planned:
                continue
            satisfied = True
            for need in needs[course]:
                if need not in planned:
                    satisfied = False
                    break
            if satisfied:
                ready.append(course)
        if not ready:
            raise ValueError("prerequisites loop back on themselves")
        ready.sort()
        term = ready[:per_term]
        terms.append(term)
        planned.update(term)
    return terms
