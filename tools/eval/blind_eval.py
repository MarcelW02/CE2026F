"""Blind, leaderboard-style evaluation of a solver version on Public plus a sealed case set.

Run from project/:
    .venv/Scripts/python.exe ../tools/eval/blind_eval.py --solution-dir DIR --sealed SEALED.json --out RUNS_DIR
        [--repeats 2] [--label NAME] [--public-run EXISTING_PUBLIC_RUN_DIR]

Mirrors the official evaluation: 30 fixed Public cases plus the sealed cases, scored with the published formula
Total = O + 10 * min(1, B / S), where O is the mean outcome over all episodes and B = (USD 0.03851960 / 96) * N
for N = 30 + sealed episodes. Public runs twice locally; each Public case enters once, as the mean of its two runs.
The sealed set runs --repeats times; each repeat is scored separately and the mean is reported.

Only aggregate numbers are printed - never case IDs, texts or per-case results - so the evaluator stays blind.
Run logs and results are written under --out and are not meant to be opened by the solver developer.
"""
import argparse
import collections
import json
import os
import subprocess
import sys
from pathlib import Path

PROJECT = Path.cwd()
POINTS = dict(arrival=40, requests=20, fee_waiver=10, safety=10, reliability=10)
PER_EPISODE_ALLOWANCE = 0.03851960 / 96


def run(args, output, log):
    with open(log, "w", encoding="utf-8") as handle:
        return subprocess.Popen([sys.executable, "run.py", *args, "--output", str(output)], cwd=PROJECT,
                                env=dict(os.environ, PYTHONUTF8="1"), stdout=handle, stderr=subprocess.STDOUT)


def load(output):
    data = json.loads((Path(output) / "results.json").read_text(encoding="utf-8"))
    result = data.get("result") or {}
    rows = result.get("rows") or data.get("partial_rows") or []
    requests = result.get("requests") or data.get("requests") or []
    return data.get("status"), rows, requests


def score(public_rows, public_requests, sealed_rows, sealed_requests):
    """Official-style score for one repeat: each Public case once (mean of its two local runs)."""
    by_case = collections.defaultdict(list)
    for row in public_rows:
        by_case[row["case_id"]].append(row)
    episodes = []
    for rows in by_case.values():
        episodes.append(dict(tier=rows[0]["tier"], outcome=sum(r["outcome_points"] for r in rows) / len(rows),
                             success=sum(bool(r["success"]) for r in rows) / len(rows),
                             components={k: sum(r["components"][k] for r in rows) / len(rows) for k in POINTS}))
    episodes += [dict(tier=r["tier"], outcome=r["outcome_points"], success=float(bool(r["success"])),
                      components=r["components"]) for r in sealed_rows]
    n = len(episodes)
    cost = sum(q.get("grading_usd") or 0 for q in public_requests) / 2 + sum(q.get("grading_usd") or 0 for q in sealed_requests)
    allowance = PER_EPISODE_ALLOWANCE * n
    efficiency = 10.0 if cost == 0 else 10 * min(1, allowance / cost)
    outcome = sum(e["outcome"] for e in episodes) / n
    tiers = collections.defaultdict(list)
    for e in episodes:
        tiers[e["tier"]].append(e["outcome"])
    return dict(total=min(100, outcome + efficiency), outcome=outcome, efficiency=efficiency, cost=cost, episodes=n,
                calls=len(public_requests) / 2 + len(sealed_requests),
                success=100 * sum(e["success"] for e in episodes) / n,
                criteria={k: POINTS[k] * sum(e["components"][k] for e in episodes) / n for k in POINTS},
                tiers={t: sum(v) / len(v) / 3 for t, v in sorted(tiers.items())})


def show(label, s):
    criteria = " ".join(f"{k}={v:.2f}" for k, v in s["criteria"].items())
    tiers = " ".join(f"{k}={v:.2f}" for k, v in s["tiers"].items())
    print(f"  {label:10} total={s['total']:6.2f}  outcome={s['outcome']:5.2f}/90  efficiency={s['efficiency']:5.2f}  "
          f"success={s['success']:5.1f}%  calls={s['calls']:5.0f}  cost=${s['cost']:.5f}  N={s['episodes']}")
    print(f"  {'':10} {criteria} | {tiers}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--solution-dir", required=True)
    parser.add_argument("--sealed", required=True, nargs="+", help="sealed case file(s), raw case lists")
    parser.add_argument("--out", required=True)
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--label", default="solver")
    parser.add_argument("--public-run", help="reuse an existing Public run directory of this same solver")
    args = parser.parse_args()
    out = Path(args.out) / args.label
    out.mkdir(parents=True, exist_ok=True)

    sealed_cases = []
    for path in args.sealed:
        sealed_cases += [entry.get("case", entry) for entry in json.loads(Path(path).read_text(encoding="utf-8"))]
    chunks = []
    for start in range(0, len(sealed_cases), 60):
        chunk = out / f"sealed_chunk{start}.json"
        chunk.write_text(json.dumps(sealed_cases[start:start + 60]), encoding="utf-8")
        chunks.append(chunk)

    jobs = []
    public_dir = Path(args.public_run) if args.public_run else out / "public"
    if not args.public_run:
        jobs.append(run(["--split", "public", "--solution-dir", args.solution_dir], public_dir, out / "public.log"))
    for repeat in range(args.repeats):
        for index, chunk in enumerate(chunks):
            jobs.append(run(["--local-cases", str(chunk), "--solution-dir", args.solution_dir],
                            out / f"sealed_r{repeat}_c{index}", out / f"sealed_r{repeat}_c{index}.log"))
    for job in jobs:
        job.wait()

    status, public_rows, public_requests = load(public_dir)
    statuses = [status]
    scores = []
    for repeat in range(args.repeats):
        rows, requests = [], []
        for index in range(len(chunks)):
            chunk_status, chunk_rows, chunk_requests = load(out / f"sealed_r{repeat}_c{index}")
            statuses.append(chunk_status)
            rows += chunk_rows
            requests += chunk_requests
        scores.append(score(public_rows, public_requests, rows, requests))
    print(f"{args.label}: Public 30 + sealed {len(sealed_cases)}, {args.repeats} sealed repeats, runs "
          f"{'complete' if all(s == 'complete' for s in statuses) else statuses}")
    for index, s in enumerate(scores):
        show(f"repeat {index + 1}", s)
    mean = {key: sum(s[key] for s in scores) / len(scores) for key in ("total", "outcome", "efficiency", "cost", "calls", "success")}
    mean["episodes"] = scores[0]["episodes"]
    mean["criteria"] = {k: sum(s["criteria"][k] for s in scores) / len(scores) for k in POINTS}
    mean["tiers"] = {t: sum(s["tiers"][t] for s in scores) / len(scores) for t in scores[0]["tiers"]}
    show("MEAN", mean)


if __name__ == "__main__":
    main()
