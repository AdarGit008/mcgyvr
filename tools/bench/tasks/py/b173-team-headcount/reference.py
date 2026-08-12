def team_headcount(chart, name):
    if not isinstance(chart, dict): raise ValueError("chart must be a mapping")
    if name not in chart: raise ValueError("the chart holds no such name")
    reports = chart[name]
    if not isinstance(reports, list): raise ValueError("the reports of a worker must be a list")
    covered = 1
    for worker in reports:
        if not isinstance(worker, str): raise ValueError("a report must be a name")
        covered += team_headcount(chart, worker)
    return covered
