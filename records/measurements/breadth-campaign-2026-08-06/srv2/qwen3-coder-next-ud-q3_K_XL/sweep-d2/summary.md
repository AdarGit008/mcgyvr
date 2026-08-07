greedy (T=0.0): 10/12 pass
sampled draw 0 (T=0.7): 11/12 pass — the price of moving off greedy

first-pass index over 12 tasks with all 8 sampled draws recorded (11 with any pass, 1 with none):

| index | tasks | cumulative pass@≤k |
|:-----:|:-----:|:------------------:|
| 0 | 11 | 11/12 |
| 1 | 0 | 11/12 |
| 2 | 0 | 11/12 |
| 3 | 0 | 11/12 |
| 4 | 0 | 11/12 |
| 5 | 0 | 11/12 |
| 6 | 0 | 11/12 |
| 7 | 0 | 11/12 |
| none | 1 | — |

wall clock per additional candidate: 25.5s dispatch + 0.3s acceptance (mean over 96 sampled draws)

108 rows. 2 replies the parser refused, 0 draws lost to dispatch errors.
