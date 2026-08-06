greedy (T=0.0): 1/20 pass
sampled draw 0 (T=0.7): 0/20 pass — the price of moving off greedy

first-pass index over 20 tasks with all 8 sampled draws recorded (2 with any pass, 18 with none):

| index | tasks | cumulative pass@≤k |
|:-----:|:-----:|:------------------:|
| 0 | 0 | 0/20 |
| 1 | 0 | 0/20 |
| 2 | 0 | 0/20 |
| 3 | 2 | 2/20 |
| 4 | 0 | 2/20 |
| 5 | 0 | 2/20 |
| 6 | 0 | 2/20 |
| 7 | 0 | 2/20 |
| none | 18 | — |

wall clock per additional candidate: 33.6s dispatch + 0.1s acceptance (mean over 160 sampled draws)

180 rows. 172 replies the parser refused, 0 draws lost to dispatch errors.
