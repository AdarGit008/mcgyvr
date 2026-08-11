def run_press(jobs: list, budget: int) -> dict:
    if not isinstance(jobs, list):
        raise ValueError("jobs must be a list")
    if not isinstance(budget, int) or isinstance(budget, bool) or budget < 0:
        raise ValueError("budget must be a non-negative whole number")
    printed, waiting, pages = [], [], 0
    for job in jobs:
        if not isinstance(job, list) or len(job) != 2 or not isinstance(job[0], str) or job[0] == "" or not isinstance(job[1], int) or isinstance(job[1], bool) or job[1] < 1:
            raise ValueError("malformed job")
        if not waiting and pages + job[1] <= budget:
            printed.append(job[0])
            pages += job[1]
        else:
            waiting.append(job[0])
    return {"printed": printed, "waiting": waiting, "pages": pages}
