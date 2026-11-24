"""Aggregated diagnostics and paired comparisons for blind_eval.py outputs. Never prints case IDs or texts.

Run from project/:
    .venv/Scripts/python.exe ../tools/eval/diagnose.py EVAL_DIR [EVAL_DIR ...]          # loss analysis
    .venv/Scripts/python.exe ../tools/eval/diagnose.py --compare BASE_DIR NEW_DIR      # paired difference

EVAL_DIR is a label folder written by blind_eval.py (containing sealed_r*_c* run folders). Several folders of the same
solver are pooled. The loss analysis shows, per tier and per author-assigned family label: episodes, success rate,
mean outcome and the outcome points lost per failed check, plus error types, cost and call types. The paired
comparison matches the same sealed case across two solvers (mean over each solver's repeats), which removes
case-to-case variation from the noise, and reports the mean difference with its standard error.
"""
import argparse
import collections
import json
import math
from pathlib import Path

POINTS = dict(arrival=40, requests=20, fee_waiver=10, safety=10, reliability=10)


def sealed_runs(folder):
    rows, requests = [], []
    for run in sorted(Path(folder).glob("sealed_r*_c*")):
        path = run / "results.json"
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        result = data.get("result") or {}
        rows += result.get("rows") or data.get("partial_rows") or []
        requests += result.get("requests") or data.get("requests") or []
    return rows, requests


def lost_points(row):
    return {key: POINTS[key] * (1 - row["components"][key]) for key in POINTS if row["components"][key] < 1}


def analyse(folders):
    rows, requests = [], []
    for folder in folders:
        more_rows, more_requests = sealed_runs(folder)
        rows += more_rows
        requests += more_requests
    print(f"pooled sealed episodes: {len(rows)} from {len(folders)} folder(s)")
    groups = collections.defaultdict(list)
    for row in rows:
        groups[(row["tier"], row.get("family") or "?")].append(row)
    print(f"  {'tier':9} {'family':38} {'eps':>4} {'success':>8} {'outcome':>8}  points lost per episode by criterion")
    tier_totals = collections.defaultdict(list)
    for (tier, family), items in sorted(groups.items(), key=lambda kv: (kv[0][0], -sum(90 - r["outcome_points"] for r in kv[1]))):
        tier_totals[tier] += items
        lost = collections.Counter()
        for row in items:
            lost.update(lost_points(row))
        per = " ".join(f"{k}={v / len(items):.1f}" for k, v in lost.most_common())
        print(f"  {tier:9} {family[:38]:38} {len(items):4} {100 * sum(r['success'] for r in items) / len(items):7.0f}% "
              f"{sum(r['outcome_points'] for r in items) / len(items):8.1f}  {per}")
    print("  per tier: " + " | ".join(f"{t} outcome {sum(r['outcome_points'] for r in v) / len(v):.1f} "
                                      f"(lost {sum(90 - r['outcome_points'] for r in v) / len(rows):.2f} of the pooled mean)"
                                      for t, v in sorted(tier_totals.items())))
    errors = collections.Counter(r.get("error_type") for r in rows if r.get("error_type"))
    print("  error types (episodes):", dict(errors) or "none")
    tier_of = {}
    for row in rows:
        tier_of[row["case_id"]] = row["tier"]
    cost, calls, full, zero = collections.Counter(), collections.Counter(), collections.Counter(), collections.Counter()
    for request in requests:
        tier = tier_of.get((request.get("label") or {}).get("case_id"), "?")
        cost[tier] += request.get("grading_usd") or 0
        calls[tier] += 1
        full[tier] += "This request asks only" not in (request.get("instructions") or "")
        zero[tier] += request.get("reasoning_tokens") == 0
    episodes = collections.Counter(row["tier"] for row in rows)
    for tier in sorted(calls):
        n = max(1, episodes[tier])
        print(f"  {tier:9} cost/episode ${cost[tier] / n:.6f}  calls/episode {calls[tier] / n:.2f}  "
              f"full-call share {100 * full[tier] / max(1, calls[tier]):.0f}%  zero-reasoning {100 * zero[tier] / max(1, calls[tier]):.0f}%")


def compare(base, new):
    def per_case(folder):
        rows, _ = sealed_runs(folder)
        outcomes = collections.defaultdict(list)
        for row in rows:
            outcomes[row["case_id"]].append((row["tier"], row["outcome_points"]))
        return {case: (values[0][0], sum(v for _, v in values) / len(values)) for case, values in outcomes.items()}

    a, b = per_case(base), per_case(new)
    shared = sorted(set(a) & set(b))
    diffs = collections.defaultdict(list)
    for case in shared:
        diffs["all"].append(b[case][1] - a[case][1])
        diffs[a[case][0]].append(b[case][1] - a[case][1])
    print(f"paired over {len(shared)} sealed cases (outcome points per episode, new minus base)")
    for key, values in sorted(diffs.items(), key=lambda kv: kv[0] != "all"):
        mean = sum(values) / len(values)
        spread = math.sqrt(sum((v - mean) ** 2 for v in values) / max(1, len(values) - 1) / len(values))
        better = sum(v > 0 for v in values)
        worse = sum(v < 0 for v in values)
        print(f"  {key:9} mean {mean:+.2f} ± {spread:.2f} (SE)  cases better {better}, worse {worse}, equal {len(values) - better - worse}"
              f"  -> total effect on the 120-episode score {mean * len(values) / 120 if key == 'all' else mean * len(values) / 120:+.2f}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("folders", nargs="*")
    parser.add_argument("--compare", nargs=2, metavar=("BASE", "NEW"))
    args = parser.parse_args()
    if args.compare:
        compare(*args.compare)
    else:
        analyse(args.folders)


if __name__ == "__main__":
    main()
