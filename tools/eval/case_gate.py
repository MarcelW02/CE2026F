"""Quality gate for authored evaluation cases: valid, consistent and provably solvable.

Run from project/:
    .venv/Scripts/python.exe ../tools/eval/case_gate.py CASES.json [--manual WITNESSES.json] [--quiet]

For every case:
  1. framework validate_case (published fields, limits and expression grammar);
  2. the truth planner (tools/eval/oracle_solution) plays it with the ground-truth rules, no model calls;
  3. the recorded actions, or a hand-written witness from --manual ({case_id: {"steps": [...]}}), are replayed
     with the framework's replay_witness, which accepts only complete travel success.

Passing cases are written to CASES.gated.json with their witnesses in CASES.witnesses.json. Without --quiet the
reason for each failure is printed for the case author; --quiet prints counts only (for blind evaluators).
"""
import argparse
import copy
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT = Path.cwd()
sys.path.insert(0, str(PROJECT))
from framework.case_submission import replay_witness  # noqa: E402
from framework.world_factory import validate_case  # noqa: E402

ORACLE = Path(__file__).resolve().parent / "oracle_solution"


def oracle_actions(cases, cases_path):
    """Run the truth planner on the cases (in chunks of 60) and return {case_id: (success, actions)}."""
    found = {}
    env = dict(os.environ, ORACLE_CASES=str(cases_path), PYTHONUTF8="1")
    with tempfile.TemporaryDirectory(prefix="case-gate-") as work:
        for start in range(0, len(cases), 60):
            chunk = Path(work) / f"chunk{start}.json"
            chunk.write_text(json.dumps(cases[start:start + 60]), encoding="utf-8")
            output = Path(work) / f"run{start}"
            with open(Path(work) / f"run{start}.log", "w", encoding="utf-8") as log:
                subprocess.run([sys.executable, "run.py", "--local-cases", str(chunk), "--solution-dir", str(ORACLE),
                                "--output", str(output)], cwd=PROJECT, env=env, stdout=log, stderr=subprocess.STDOUT)
            results = output / "results.json"
            if not results.exists():
                continue
            data = json.loads(results.read_text(encoding="utf-8"))
            rows = (data.get("result") or {}).get("rows") or data.get("partial_rows") or []
            for row in rows:
                found[row["case_id"]] = (row.get("success") is True, row.get("observed_action_sequence") or [],
                                         [key for key, value in (row.get("checks") or {}).items() if not value],
                                         row.get("error_type"))
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("cases")
    parser.add_argument("--manual", help="hand-written witnesses {case_id: {steps: [...]}} for timing-tight cases")
    parser.add_argument("--quiet", action="store_true", help="print counts only")
    args = parser.parse_args()
    path = Path(args.cases).resolve()
    data = json.loads(path.read_text(encoding="utf-8"))
    cases = [entry.get("case", entry) for entry in data]
    manual = json.loads(Path(args.manual).read_text(encoding="utf-8")) if args.manual else {}

    problems, valid = {}, []
    for case in cases:
        try:
            validate_case(copy.deepcopy(case))
            valid.append(case)
        except Exception as error:  # noqa: BLE001 - report every validation failure to the author
            problems[case.get("case_id", "?")] = f"invalid case: {error}"
    played = oracle_actions(valid, path) if valid else {}

    passed, witnesses = [], {}
    for case in valid:
        identifier = case["case_id"]
        attempts = []
        if identifier in manual:
            attempts.append(("manual witness", manual[identifier]))
        success, actions, failed, error = played.get(identifier, (False, [], ["not run"], None))
        if actions:
            attempts.append(("truth planner", {"steps": actions, "expected_success": True}))
        reasons = [] if success or identifier in manual else [f"truth planner failed {failed} {error or ''}".strip()]
        for label, witness in attempts:
            try:
                replay_witness(copy.deepcopy(case), witness)
                passed.append(case)
                witnesses[identifier] = witness
                break
            except Exception as replay_error:  # noqa: BLE001
                reasons.append(f"{label} replay: {replay_error}")
        else:
            problems[identifier] = "; ".join(reasons) or "no witness"

    path.with_suffix(".gated.json").write_text(json.dumps(passed, indent=1), encoding="utf-8")
    path.with_suffix(".witnesses.json").write_text(json.dumps(witnesses, indent=1), encoding="utf-8")
    print(f"cases={len(cases)} valid={len(valid)} solvable={len(passed)} rejected={len(problems)}")
    if not args.quiet:
        for identifier, reason in problems.items():
            print(f"  REJECTED {identifier}: {reason}")
        tiers = {}
        for case in passed:
            tiers[case["difficulty"]] = tiers.get(case["difficulty"], 0) + 1
        print("  passing cases per tier:", tiers)


if __name__ == "__main__":
    main()
