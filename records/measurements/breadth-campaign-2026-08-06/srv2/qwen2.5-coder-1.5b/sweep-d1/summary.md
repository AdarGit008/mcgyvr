greedy (T=0.0): 7/20 pass
sampled draw 0 (T=0.7): 5/20 pass — the price of moving off greedy

first-pass index over 20 tasks with all 8 sampled draws recorded (11 with any pass, 9 with none):

| index | tasks | cumulative pass@≤k |
|:-----:|:-----:|:------------------:|
| 0 | 5 | 5/20 |
| 1 | 2 | 7/20 |
| 2 | 1 | 8/20 |
| 3 | 0 | 8/20 |
| 4 | 0 | 8/20 |
| 5 | 0 | 8/20 |
| 6 | 3 | 11/20 |
| 7 | 0 | 11/20 |
| none | 9 | — |

wall clock per additional candidate: 1.6s dispatch + 0.1s acceptance (mean over 160 sampled draws)

180 rows. 0 replies the parser refused, 0 draws lost to dispatch errors.
