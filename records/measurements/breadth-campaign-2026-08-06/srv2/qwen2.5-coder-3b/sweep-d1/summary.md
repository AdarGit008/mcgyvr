greedy (T=0.0): 12/20 pass
sampled draw 0 (T=0.7): 10/20 pass — the price of moving off greedy

first-pass index over 20 tasks with all 8 sampled draws recorded (15 with any pass, 5 with none):

| index | tasks | cumulative pass@≤k |
|:-----:|:-----:|:------------------:|
| 0 | 10 | 10/20 |
| 1 | 4 | 14/20 |
| 2 | 0 | 14/20 |
| 3 | 1 | 15/20 |
| 4 | 0 | 15/20 |
| 5 | 0 | 15/20 |
| 6 | 0 | 15/20 |
| 7 | 0 | 15/20 |
| none | 5 | — |

wall clock per additional candidate: 2.0s dispatch + 0.3s acceptance (mean over 160 sampled draws)

180 rows. 1 replies the parser refused, 0 draws lost to dispatch errors.
