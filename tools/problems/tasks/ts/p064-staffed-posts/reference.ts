export function staffedPosts(wanted: number[][], posts: number): number {
  if (!Number.isInteger(posts) || posts < 1) {
    throw new Error("posts must be a positive integer");
  }
  if (!Array.isArray(wanted)) {
    throw new Error("wanted must be an array of applicants");
  }
  for (const listed of wanted) {
    if (!Array.isArray(listed)) {
      throw new Error("each applicant is an array of post numbers");
    }
    for (const post of listed) {
      if (!Number.isInteger(post) || post < 0 || post >= posts) {
        throw new Error("post numbers must be integers from 0 to posts-1");
      }
    }
  }
  const holder: number[] = new Array(posts).fill(-1);
  const place = (applicant: number, visited: Set<number>): boolean => {
    for (const post of wanted[applicant]) {
      if (visited.has(post)) {
        continue;
      }
      visited.add(post);
      if (holder[post] === -1 || place(holder[post], visited)) {
        holder[post] = applicant;
        return true;
      }
    }
    return false;
  };
  let staffed = 0;
  for (let applicant = 0; applicant < wanted.length; applicant++) {
    if (place(applicant, new Set())) {
      staffed += 1;
    }
  }
  return staffed;
}
