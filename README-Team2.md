# Team 2 travel solver (v10)

The final solver passed **60 of 60 Public episodes** and scored **100/100** in two runs with the course runner.

## Changes from the v10 starter

- Switched from GPT‑5.6 Luna with multiple model roles to GPT‑6 Luna with one interpreter. Enabled selective refresh so the solver can apply new notices and keep rules that still apply.
- Added Python rules for supported spending permissions, arrival deadlines, amendments, weather updates, and refund clauses. The refund rules account for cancellation time and observed delays.
- Narrowed the observation sent to the model to the virtual minute, tier, notices, and source references. Used short references for consent codes and restored the exact codes before passing them back to the controller.
- Updated the interpreter prompt to preserve conditional exceptions and extract exact consent and hotel-waiver evidence. The course controller still handles search, bookings, and verification.

The implementation changes are in [config.py](project/solution/config.py), [policy.py](project/solution/policy.py), and [prompts.py](project/solution/prompts.py).

## Benchmark results

| Split | Solver | Successful episodes | Outcome points | Model calls | Grading cost (USD) | Public score |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Dev | v10 starter | 3/9 | 40/90 | 21 | $0.02566 | — |
| Dev | Final | 9/9 | 90/90 | 18 | $0.01209 | — |
| Public | First full run with one interpreter and refresh | 56/60 | 86.17/90 | 99 | $0.15355 | 87.73/100 |
| Public | GPT‑6 Luna with weather handling | 60/60 | 90/90 | 80 | $0.05089 | 94.73/100 |
| Public | Added local parsing of initial contracts | 60/60 | 90/90 | 40 | $0.02824 | 98.52/100 |
| Public | Final, run 1 | 60/60 | 90/90 | 20 | $0.01507 | 100/100 |
| Public | Final, run 2 | 60/60 | 90/90 | 20 | $0.01428 | 100/100 |

We ran the unmodified starter on Dev. The first full Public run used the intermediate solver shown in the table. Public scores include the course runner’s cost component. These are local benchmark results. The TA runs the official evaluation.

Follow the [course setup instructions](README.md#start-here) to run the benchmarks.
