/** Sliding-window maximum via a monotonically decreasing deque of indices. */
export function maxSlidingWindow(nums: number[], k: number): number[] {
  if (!Number.isInteger(k) || k < 1 || k > nums.length) {
    throw new Error("k must be an integer with 1 <= k <= nums.length");
  }
  const result: number[] = [];
  const deque: number[] = []; // indices; their values are strictly decreasing
  let head = 0; // logical front of the deque (avoids O(n) shift)
  for (let i = 0; i < nums.length; i++) {
    while (deque.length > head && nums[deque[deque.length - 1]] <= nums[i]) {
      deque.pop();
    }
    deque.push(i);
    if (deque[head] <= i - k) {
      head += 1;
    }
    if (i >= k - 1) {
      result.push(nums[deque[head]]);
    }
  }
  return result;
}
