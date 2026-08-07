greedy (T=0.0): 7/20 pass
sampled draw 0 (T=0.7): 6/20 pass — the price of moving off greedy

first-pass index over 20 tasks with all 8 sampled draws recorded (10 with any pass, 10 with none):

| index | tasks | cumulative pass@≤k |
|:-----:|:-----:|:------------------:|
| 0 | 6 | 6/20 |
| 1 | 1 | 7/20 |
| 2 | 1 | 8/20 |
| 3 | 1 | 9/20 |
| 4 | 0 | 9/20 |
| 5 | 0 | 9/20 |
| 6 | 0 | 9/20 |
| 7 | 1 | 10/20 |
| none | 10 | — |

wall clock per additional candidate: 2.6s dispatch + 0.1s acceptance (mean over 160 sampled draws)

180 rows. 0 replies the parser refused, 0 draws lost to dispatch errors.
