# ORPO vs DPO — Trade-offs for TRANC3 Personality Work

## Quick Comparison

| Aspect                      | DPO                              | ORPO                                      |
|-----------------------------|----------------------------------|-------------------------------------------|
| Core idea                   | Preference optimisation only     | Combines SFT + preference in one loss     |
| Typical pipeline            | SFT → DPO                        | Often single stage                        |
| Maturity & documentation    | Very high                        | Growing rapidly                           |
| Stability on small data     | Good with care                   | Often more stable                         |
| Hyperparameter sensitivity  | Moderate                         | Generally lower                           |
| Recommendation for v0.9.0   | **Start here**                   | Experiment after first adapters work      |

## Practical Advice for TRANC3

1. Begin with classic **DPO** after a short SFT stage — most examples and tooling support it.
2. Once the data pipeline and evaluation are solid, try **ORPO** on the same data to compare stability and simplicity.
3. Keep both options available in the training scripts so future trait adapters can choose the better method.
