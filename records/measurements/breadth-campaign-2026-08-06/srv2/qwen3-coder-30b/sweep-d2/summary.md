greedy (T=0.0): 9/12 pass
sampled draw 0 (T=0.7): 9/12 pass — the price of moving off greedy

first-pass index over 12 tasks with all 8 sampled draws recorded (11 with any pass, 1 with none):

| index | tasks | cumulative pass@≤k |
|:-----:|:-----:|:------------------:|
| 0 | 9 | 9/12 |
| 1 | 0 | 9/12 |
| 2 | 1 | 10/12 |
| 3 | 0 | 10/12 |
| 4 | 0 | 10/12 |
| 5 | 0 | 10/12 |
| 6 | 0 | 10/12 |
| 7 | 1 | 11/12 |
| none | 1 | — |

wall clock per additional candidate: 14.9s dispatch + 0.2s acceptance (mean over 96 sampled draws)

108 rows. 0 replies the parser refused, 0 draws lost to dispatch errors.
