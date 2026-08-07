greedy (T=0.0): 15/20 pass
sampled draw 0 (T=0.7): 14/20 pass — the price of moving off greedy

first-pass index over 20 tasks with all 8 sampled draws recorded (17 with any pass, 3 with none):

| index | tasks | cumulative pass@≤k |
|:-----:|:-----:|:------------------:|
| 0 | 14 | 14/20 |
| 1 | 2 | 16/20 |
| 2 | 0 | 16/20 |
| 3 | 0 | 16/20 |
| 4 | 0 | 16/20 |
| 5 | 0 | 16/20 |
| 6 | 0 | 16/20 |
| 7 | 1 | 17/20 |
| none | 3 | — |

wall clock per additional candidate: 5.8s dispatch + 0.1s acceptance (mean over 160 sampled draws)

180 rows. 0 replies the parser refused, 0 draws lost to dispatch errors.
