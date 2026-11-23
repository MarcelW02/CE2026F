# Blind evaluation tools

Local tools for an objective, leaderboard-like test of solver versions. None of this is submitted.

**Why.** Our earlier stress banks were written by the same agent that tuned the solver, from the same templates.
Every version that passed them lowered the leaderboard score (91.04 → 89.14 → 84.67). This setup separates case
authoring from solver development and checks the test set against the real leaderboard before trusting it.

## Protocol

1. **Specification.** Cases follow the published scope in `project/BENCHMARK.md` ("Supported condition
   combinations"), `project/CASE_GUIDE.md` and the course slides, not our solver or earlier stress banks.
2. **Independent authoring.** A separate author (a fresh agent without access to `project/solution/`, `tools/`
   other than this folder, or `EXPERIMENT-LOG.md`, and/or teammates) writes the cases into
   `project/local_cases/sealed/` (gitignored).
3. **Quality gate.** `case_gate.py` keeps only cases that pass the framework validator and whose solvability is
   proven by a witness replayed with the framework's `replay_witness` (the official team-case check). The witness
   comes from the truth planner (`oracle_solution/`: the supplied planner fed the ground-truth rules) or is
   hand-written for timing-tight cases (`--manual`).
4. **Blindness.** The solver developer never opens sealed case files, gate details or run logs. `blind_eval.py`
   prints aggregate scores only. A small open set may be kept separately for debugging.
5. **Calibration (go/no-go).** Before the set is trusted, it must rank the three versions with known leaderboard
   results as the leaderboard did: Louisa `443103b` (91.04) > `f70eb4e` (89.14) > `e39fc77` (84.67), including the
   Basic drop of `e39fc77`.
6. **Use.** Starting from Louisa's version, add one change group at a time; keep only gains larger than the
   measured run-to-run noise; confirm kept steps on the leaderboard.

## Commands (from `project/`)

```
.venv/Scripts/python.exe ../tools/eval/case_gate.py local_cases/sealed/batch1.json [--manual hand.json] [--quiet]
.venv/Scripts/python.exe ../tools/eval/blind_eval.py --solution-dir DIR --sealed local_cases/sealed/batch1.gated.json \
    --out C:/Users/<you>/ce2026f-runs/blind --label NAME [--repeats 2] [--public-run EXISTING_PUBLIC_RUN]
```

The truth planner uses the supplied planner, so it cannot solve cases whose timing that planner misses (for
example a notice before minute 8 with the first booking due at minute 12). Teams prove their own cases with their
own solvers, which are mostly built on the same planner, so such cases are probably rare in the official set.
Supply a hand-written witness when a valid case needs faster actions.
