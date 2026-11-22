# Team 2 travel solver (v10)

The current solver (`eb357ec`) passed **60 of 60 Public episodes** and scored **97.92/100** in the November 16 local run. It earned all 90 outcome points. Its $0.03038830 grading cost exceeded the $0.02407475 Public allowance for full efficiency credit.

## Changes from the v10 starter

- Uses GPT-6 Luna with one interpreter and selective refresh. The model reads the current authorities and their observed links. Python validates and evaluates the spending, arrival, and refund expressions against live quotes and holds.
- Reviews suspect spending and arrival rules field by field. It checks which delay activates an allowance, which tickets qualify, and whether a draft incorrectly subtracts transfer from the stated client deadline. A follow-up retries only a field that fails validation.
- Compiles Forecast fare rules by source and version for reuse across compatible inventory updates. On the booking-first path, it interprets purchase-time refund terms when a plausible replacement needs them.
- Applies scoped amendments and weather updates while preserving rules that still apply. Forecast planning can evaluate simultaneous delays together before deciding whether to hold a backup. Consent references are restored to the literal approval codes, and waiver evidence is checked against the current bulletin.

The implementation changes are in [config.py](project/solution/config.py), [policy.py](project/solution/policy.py), and [prompts.py](project/solution/prompts.py).

## Local benchmark results

| Split | Solver | Successful episodes | Outcome points | Model calls | Grading cost (USD) | Public score |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Dev | Baseline (unmodified staff v10 starter) | 3/9 | 40/90 | 21 | $0.02566 | — |
| Dev | Current solver | 9/9 | 90/90 | 21 | $0.00484690 | — |
| Public | Baseline (our first full Public run) | 56/60 | 86.17/90 | 99 | $0.15355 | 87.73/100 |
| Public | Earlier wording-specific candidate (two runs) | 60/60 each | 90/90 each | 20 each | $0.01507370 and $0.01428070 | 100/100 each |
| Public | Current solver | 60/60 | 90/90 | 133 | $0.03038830 | 97.92/100 |

We ran the unmodified staff v10 starter on Dev only. The first Public baseline already used one interpreter, context refresh, and a prompt that asked for exact consent and hotel-waiver evidence. The earlier 100/100 candidate used parsers tied to specific contract wording. The TA runs the official evaluation.

For the current implementation and verification details, see the [experiment log](EXPERIMENT-LOG.md#current-solver-verification). Follow the [course setup instructions](README.md#start-here) to run the benchmarks.
