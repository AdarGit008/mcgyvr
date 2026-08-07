def staffed_posts(wanted, posts):
    if isinstance(posts, bool) or not isinstance(posts, int) or posts < 1:
        raise ValueError("posts must be a positive integer")
    if not isinstance(wanted, list):
        raise ValueError("wanted must be a list of applicants")
    for listed in wanted:
        if not isinstance(listed, list):
            raise ValueError("each applicant is a list of post numbers")
        for post in listed:
            if (
                isinstance(post, bool)
                or not isinstance(post, int)
                or post < 0
                or post >= posts
            ):
                raise ValueError("post numbers must be integers from 0 to posts-1")
    holder = [-1] * posts

    def place(applicant, visited):
        for post in wanted[applicant]:
            if post in visited:
                continue
            visited.add(post)
            if holder[post] == -1 or place(holder[post], visited):
                holder[post] = applicant
                return True
        return False

    staffed = 0
    for applicant in range(len(wanted)):
        if place(applicant, set()):
            staffed += 1
    return staffed
