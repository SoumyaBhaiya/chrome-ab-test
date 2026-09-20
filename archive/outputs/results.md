# experiment results

Seed: `42`. Profiles per group: **7,000**. Monte Carlo replications per scenario: **5,000**.

| Planning quantity | Value |
| --- | --- |
| Primary sample requirement | 5,527 per group |
| Approximate accuracy sample requirement | 6,852 per group |
| Selected total sample | 14,000 |
| Approximate primary power at selected sample | 95.4% |
| Approximate accuracy-gate power at selected sample | 90.5% |

**Estimates from one generated dataset per scenario**

| Scenario | Control timely | Treatment timely | Lift, pp | 95% CI, pp | Primary p |
| --- | --- | --- | --- | --- | --- |
| no_effect | 59.44% | 58.99% | -0.46 | [-2.09, +1.17] | 0.5821 |
| target_effect | 60.19% | 62.24% | +2.06 | [+0.44, +3.67] | 0.0125 |
| small_effect | 59.43% | 62.39% | +2.96 | [+1.34, +4.57] | 0.0003367 |
| primary_harm | 59.91% | 56.50% | -3.41 | [-5.05, -1.78] | 4.215e-05 |
| accuracy_harm | 60.01% | 62.57% | +2.56 | [+0.94, +4.17] | 0.001897 |
| accuracy_boundary | 61.59% | 63.14% | +1.56 | [-0.05, +3.16] | 0.05724 |

**Accuracy and the complete decision**

| Scenario | Accuracy change, pp | One-sided lower bound, pp | Accuracy gate | Decision |
| --- | --- | --- | --- | --- |
| no_effect | -0.49 | -1.60 | Pass | Do not advance |
| target_effect | -0.07 | -1.18 | Pass | Advance to real validation |
| small_effect | +1.24 | +0.14 | Pass | Advance to real validation |
| primary_harm | +0.07 | -1.04 | Pass | Do not advance |
| accuracy_harm | -4.17 | -5.32 | Not established | Do not advance |
| accuracy_boundary | -2.99 | -4.11 | Not established | Do not advance |

**Repeated-experiment validation**

| Scenario | Reject primary H0 | Significant benefit | Pass accuracy | Pass both | Primary CI coverage |
| --- | --- | --- | --- | --- | --- |
| no_effect | 4.98% | 2.44% | 90.70% | 2.44% | 95.02% |
| target_effect | 95.26% | 95.26% | 90.84% | 88.34% | 95.10% |
| small_effect | 23.92% | 23.86% | 90.22% | 23.78% | 94.58% |
| primary_harm | 94.90% | 0.00% | 91.46% | 0.00% | 94.96% |
| accuracy_harm | 95.64% | 95.64% | 0.00% | 0.00% | 95.52% |
| accuracy_boundary | 95.18% | 95.18% | 4.68% | 4.68% | 94.82% |

For the target scenario, the estimated probability of passing both gates is **88.34%**, with a 95% Monte Carlo Wilson interval of **[87.42%, 89.20%]**.

Primary rejection includes significant effects in either direction. A negative effect never qualifies as a benefit. At the accuracy boundary, an accuracy-gate pass is a false noninferiority declaration. Finite simulations fluctuate around their theoretical probabilities.


![Power and joint decision probability](power_curve.png)

![Synthetic effect estimates](effect_estimates.png)
