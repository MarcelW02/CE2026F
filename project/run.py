"""Common published/local runner. Edit solution files instead of this entrypoint."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path

from framework.fp_cases import FP_DEV_CASES, FP_PUBLIC_CASES, FP_VERSION, FP_SCORE_VERSION, FP_SCORE_MAX
from framework.fp_inputs import select_cases, load_local_cases
from framework.fp_cases import fp_hash
from framework.fp_world import FP_TOOL_CONTRACT_REVISION
from framework.world_factory import world_for_case
from framework.episode_runtime import IsolatedEvaluator, EXECUTION_PROTOCOL
from framework.fp_baseline import FP_BASELINE
from framework.fp_evaluation import evaluate_travel, grade_travel
from framework.runtime import load_solution, check_protected
from framework.reporting import save_report

ROOT = Path(__file__).resolve().parent


def offline_demo():
    world = world_for_case(FP_DEV_CASES[3])
    source_id = world.observe()["operational_sources"]["budget_limit"]["id"]
    before = world.call("read", id=source_id)["source"]
    world.call("wait", minutes=14)
    after = world.call("read", id=source_id)["source"]
    print("Offline simulator inspection: zero API calls; no model grade.")
    print(json.dumps(dict(before=before, notices=world.observe()["notices"], after=after), indent=2))


def main():
    p = argparse.ArgumentParser(description="Run the travel policy on public information.")
    inputs = p.add_mutually_exclusive_group()
    inputs.add_argument("--split", choices=("dev", "public"), help="Published case bank; default: dev.")
    inputs.add_argument("--local-cases", type=Path, help="Student-authored JSON cases; diagnostic only.")
    p.add_argument("--tier", choices=("basic", "reactive", "forecast"), help="Diagnostic difficulty filter.")
    p.add_argument("--limit", type=int, help="Diagnostic subset; no local Public /100 score.")
    p.add_argument("--offline", action="store_true", help="Local source-change demo, zero model requests.")
    p.add_argument("--solution-dir", type=Path, default=ROOT, help="Folder containing the three solution modules.")
    p.add_argument("--output", type=Path, required=False, help="Fresh directory for JSON/CSV/HTML outputs.")
    args = p.parse_args()
    if args.offline: offline_demo(); return
    if args.limit is not None and args.limit < 1: p.error("--limit must be positive.")
    split = "local" if args.local_cases else args.split or "dev"
    try:
        cases = load_local_cases(args.local_cases) if args.local_cases else select_cases(split, args.tier)
        if args.local_cases and args.tier:
            cases = [case for case in cases if case["difficulty"] == args.tier]
        if not cases: raise ValueError("No cases match the selected difficulty.")
    except ValueError as error: p.error(str(error))
    if args.limit is not None: cases = cases[:args.limit]
    output = args.output or ROOT / "runs" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    if output.exists(): p.error("Choose a fresh output directory; preserve earlier attempts.")
    changes = check_protected(ROOT)
    if changes: print("Protected source changes require review/rerun:", changes)
    with load_solution(args.solution_dir) as (cfg, route, solver, digest, sources):
        repeats = 2 if split == "public" else 1
        key = None; api = None
        if cfg["architecture"] != "rules":
            from dotenv import dotenv_values
            key = os.environ.get("OPENAI_API_KEY") or dotenv_values(ROOT / ".env").get("OPENAI_API_KEY")
            if not key or key == "PASTE_YOUR_KEY_HERE": raise ValueError("Set the instructor-issued OPENAI_API_KEY in .env.")
        report = dict(version=FP_VERSION, scoring_version=FP_SCORE_VERSION,
            tool_contract_revision=FP_TOOL_CONTRACT_REVISION,
            split=split, tier_filter=args.tier,
            local_cases_file=str(args.local_cases) if args.local_cases else None,
            instance_fingerprints={case["case_id"]: fp_hash(case) for case in cases},
            observed_at=datetime.now(timezone.utc).isoformat(),
            config=cfg, implementation_sha256=digest, solution_sources=sources,
            protected_changes=changes, partial_rows=[], requests=[], status="running",
            execution_protocol=EXECUTION_PROTOCOL)
        print("Cases:", len(cases), "Repeats:", repeats, "Common tool slots: 3")
        print("Paid guards: 1000 calls / USD 2. Timeout: 180s. Automatic retries: 0.")
        print("Configuration:", json.dumps(cfg, indent=2))
        with IsolatedEvaluator(sources, cfg, key) as evaluator:
            def progress(row):
                report["partial_rows"].append(row)
                report["requests"] = evaluator.snapshot()["records"]
                save_report(output, report, key)
                print(row["case_id"], row["repeat"], "quality:", row["quality"], "error:", row["error_type"], flush=True)
            try:
                result = evaluator.evaluate(cases, repeats=repeats, progress=progress)
                report["result"] = result; report["status"] = result["status"]
                if split == "public" and args.limit is None and args.tier is None and result["complete"] and result["usage"]["estimated_usd"] is not None:
                    report["grade"] = grade_travel(result, FP_BASELINE)
                    print("Local Public development score:", round(report["grade"]["score"], 2), "/", FP_SCORE_MAX)
                    print("Criterion points:", json.dumps(report["grade"]["criterion_points"]))
                    print("Difficulty contributions:", json.dumps({tier: summary["outcome_contribution"]
                        for tier, summary in report["grade"]["tiers"].items()}), "/ 30 each")
                else:
                    print("Diagnostic or interrupted run: no local Public /100 score.")
                    if result["complete"]:
                        print("Mean travel outcome:", round(result["outcome_points"], 2), "/ 90")
                        print("Difficulty outcomes:", json.dumps({tier: summary["outcome_points"]
                            for tier, summary in result["tiers"].items()}), "/ 90")
                print("Usage and estimated API cost:", json.dumps(result["usage"]))
                print("Cache-neutral grading cost:", result["usage"].get("grading_usd"), "USD; not an invoice.")
            except Exception as exc:
                report["status"] = "interrupted"
                report["error_type"] = type(exc).__name__
                raise
            finally:
                snapshot = evaluator.snapshot()
                report["requests"] = snapshot["records"]
                report["pending_requests"] = snapshot["pending_requests"]
                report["worker_failures"] = evaluator.failures
                save_report(output, report, key)
        print("Inspect:", output / "report.html")


if __name__ == "__main__": main()
