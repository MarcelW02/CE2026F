"""Summarize and compare local runs: outcomes, failures and where API cost goes.

Usage (from project/):
    .venv/Scripts/python.exe ../tools/run_summary.py runs/public_baseline_eb357ec
    .venv/Scripts/python.exe ../tools/run_summary.py runs/A runs/B --cases

Reads only results.json files written by run.py; makes no API calls. Not part
of the submitted solver (submit.py packages solution/ only).
"""
import argparse
import collections
import json
from pathlib import Path

# Staff allowance per episode (README section 7): USD 0.03851960 / 96.
ALLOWANCE_PER_EPISODE = 0.03851960 / 96


def load(run_dir):
    path = Path(run_dir) / "results.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    result = data.get("result") or {}
    rows = result.get("rows") or data.get("partial_rows") or []
    requests = result.get("requests") or data.get("requests") or []
    return data, result, rows, requests


def stage_of(label):
    label = label or {}
    stage = label.get("stage") or label.get("role") or "?"
    if label.get("attempt"):
        stage += "/" + label["attempt"]
    return stage


def load_many(run_dirs):
    """Merge several runs (for example one per tier) into one combined view."""
    rows, requests, statuses = [], [], []
    for run_dir in run_dirs:
        data, _, run_rows, run_requests = load(run_dir)
        rows += run_rows
        requests += run_requests
        statuses.append(data.get("status"))
    first = load(run_dirs[0])[0]
    status = "complete" if all(s == "complete" for s in statuses) else "/".join(map(str, statuses))
    return dict(first, status=status, split=first.get("split")), {}, rows, requests


def summarize(run_dir, show_cases=False, combined=None):
    data, result, rows, requests = combined or load(run_dir)
    n = len(rows)
    print("=" * 78)
    print(f"{run_dir}  status={data.get('status')}  split={data.get('split')}  "
          f"impl={str(data.get('implementation_sha256'))[:12]}")
    if data.get("protected_changes"):
        print("  WARNING protected files differ:", len(data["protected_changes"]))
    if not n:
        print("  no episode rows")
        return
    outcome = sum(r["outcome_points"] for r in rows) / n
    successes = sum(1 for r in rows if r.get("success"))
    cost = sum(q.get("grading_usd") or 0 for q in requests)
    per_episode = cost / n
    efficiency = 10.0 if cost == 0 else 10 * min(1, ALLOWANCE_PER_EPISODE * n / cost)
    print(f"  episodes={n}  success={successes}/{n}  outcome={outcome:.2f}/90  "
          f"projected total={min(100, outcome + efficiency):.2f}")
    print(f"  calls={len(requests)} ({len(requests) / n:.2f}/episode)  grading=${cost:.5f}  "
          f"per episode=${per_episode:.6f} vs allowance ${ALLOWANCE_PER_EPISODE:.6f} "
          f"({per_episode / ALLOWANCE_PER_EPISODE:.2f}x)  efficiency={efficiency:.2f}/10")

    tiers = collections.defaultdict(list)
    for r in rows:
        tiers[r.get("tier") or r.get("difficulty")].append(r)
    tier_of = {r["case_id"]: (r.get("tier") or r.get("difficulty")) for r in rows}
    tier_cost = collections.Counter()
    for q in requests:
        tier_cost[tier_of.get((q.get("label") or {}).get("case_id"), "?")] += q.get("grading_usd") or 0
    for tier, items in sorted(tiers.items()):
        mean = sum(r["outcome_points"] for r in items) / len(items)
        ok = sum(1 for r in items if r.get("success"))
        print(f"  {tier:9} {ok}/{len(items)} success  outcome={mean:.2f}/90  "
              f"cost/episode=${tier_cost[tier] / len(items):.6f}")

    failures = [r for r in rows if not r.get("success")]
    if failures:
        print("  failures:")
        for r in failures:
            failed = [k for k, v in (r.get("checks") or {}).items() if not v]
            print(f"    {r['case_id']} rep{r.get('repeat')} [{r.get('tier')}] "
                  f"{r['outcome_points']:.1f}/90 failed={failed} error={r.get('error_type')}")

    stages = collections.defaultdict(lambda: [0, 0, 0, 0, 0.0])
    for q in requests:
        s = stages[stage_of(q.get("label"))]
        s[0] += 1
        s[1] += q.get("input_tokens") or 0
        s[2] += q.get("output_tokens") or 0
        s[3] += q.get("reasoning_tokens") or 0
        s[4] += q.get("grading_usd") or 0
    print("  cost by stage:            calls   input  output reasoning   grading  share")
    for name, (c, i, o, rz, g) in sorted(stages.items(), key=lambda kv: -kv[1][4]):
        print(f"    {name[:24]:24} {c:5} {i:7} {o:7} {rz:9}  ${g:.5f} {g / cost * 100 if cost else 0:5.1f}%")
    out = sum(q.get("output_tokens") or 0 for q in requests) * 0.50 / 1e6
    print(f"  output-token share of grading cost: {out / cost * 100 if cost else 0:.1f}%")

    if show_cases:
        per_case = collections.defaultdict(lambda: [0, 0.0])
        for q in requests:
            key = (q.get("label") or {}).get("case_id")
            per_case[key][0] += 1
            per_case[key][1] += q.get("grading_usd") or 0
        repeats = collections.Counter(r["case_id"] for r in rows)
        print("  cost by case (all repeats):")
        for case, (c, g) in sorted(per_case.items(), key=lambda kv: -kv[1][1]):
            print(f"    {str(case):34} [{tier_of.get(case, '?'):8}] calls={c:3} "
                  f"per episode=${g / max(1, repeats[case]):.6f}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("runs", nargs="+", help="run directories containing results.json")
    parser.add_argument("--cases", action="store_true", help="also list cost per case")
    parser.add_argument("--combine", action="store_true",
                        help="treat all given runs as one (e.g. per-tier runs of one Public pass)")
    args = parser.parse_args()
    if args.combine:
        summarize(" + ".join(args.runs), args.cases, combined=load_many(args.runs))
        return
    for run in args.runs:
        summarize(run, args.cases)


if __name__ == "__main__":
    main()
