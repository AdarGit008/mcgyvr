greedy (T=0.0): 12/20 pass
sampled draw 0 (T=0.7): 14/20 pass — the price of moving off greedy

first-pass index over 20 tasks with all 8 sampled draws recorded (16 with any pass, 4 with none):

| index | tasks | cumulative pass@≤k |
|:-----:|:-----:|:------------------:|
| 0 | 14 | 14/20 |
| 1 | 1 | 15/20 |
| 2 | 0 | 15/20 |
| 3 | 1 | 16/20 |
| 4 | 0 | 16/20 |
| 5 | 0 | 16/20 |
| 6 | 0 | 16/20 |
| 7 | 0 | 16/20 |
| none | 4 | — |

wall clock per additional candidate: 4.0s dispatch + 0.1s acceptance (mean over 160 sampled draws)

180 rows. 0 replies the parser refused, 0 draws lost to dispatch errors.
