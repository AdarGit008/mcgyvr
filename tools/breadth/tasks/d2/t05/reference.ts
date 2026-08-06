/** First and last index of target in a sorted array, via two binary searches. */
export function searchRange(nums: number[], target: number): [number, number] {
  // Smallest index whose value is >= target (or nums.length).
  function lowerBound(): number {
    let lo = 0;
    let hi = nums.length;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (nums[mid] < target) {
        lo = mid + 1;
      } else {
        hi = mid;
      }
    }
    return lo;
  }
  // Smallest index whose value is > target (or nums.length).
  function upperBound(): number {
    let lo = 0;
    let hi = nums.length;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (nums[mid] <= target) {
        lo = mid + 1;
      } else {
        hi = mid;
      }
    }
    return lo;
  }
  const first = lowerBound();
  if (first === nums.length || nums[first] !== target) {
    return [-1, -1];
  }
  return [first, upperBound() - 1];
}
