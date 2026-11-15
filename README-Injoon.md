# Team 2 travel solver (v10)

The final solver passed **60 of 60 Public episodes** and scored **100/100** in two runs with the course runner.

## Changes from the v10 starter

- Switched from GPT‑5.6 Luna with multiple model roles to GPT‑6 Luna with one interpreter. Enabled selective refresh so the solver can apply new notices and keep rules that still apply.
- Added Python rules for supported spending permissions, arrival deadlines, amendments, weather updates, and refund clauses. The refund rules account for cancellation time and observed delays.
- Narrowed the observation sent to the model to the virtual minute, tier, notices, and source references. Used short references for consent codes and restored the exact codes before passing them back to the controller.
- Updated the interpreter prompt to preserve conditional exceptions and extract exact consent and hotel-waiver evidence. The course controller still handles search, bookings, and verification.

The implementation changes are in [config.py](project/solution/config.py), [policy.py](project/solution/policy.py), and [prompts.py](project/solution/prompts.py).

## Benchmark vs. final solver

| Split | Solver | Successful episodes | Outcome points | Model calls | Grading cost (USD) | Public score |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Dev | v10 starter | 3/9 | 40/90 | 21 | $0.02566 | — |
| Dev | Final | 9/9 | 90/90 | 18 | $0.01209 | — |
| Public | Benchmark reference | 56/60 | 86.17/90 | 99 | $0.15355 | 87.73/100 |
| Public | Final (two runs) | 60/60 each | 90/90 each | 20 each | $0.01507 and $0.01428 | 100/100 each |

The Public reference is our first full run with one interpreter and context refresh. We evaluated the unmodified v10 starter on Dev. These are local results from the course runner. The TA runs the official evaluation.

See the [experiment log](EXPERIMENT-LOG.md) for intermediate results and discarded changes. Follow the [course setup instructions](README.md#start-here) to run the benchmarks.
