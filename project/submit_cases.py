"""Create the five-case JSON ZIP submitted together with the three-file solver ZIP."""
import argparse
import json
from pathlib import Path
from framework.case_submission import TEAM_IDS, read_json, witnesses_from_report, write_pack

ROOT = Path(__file__).resolve().parent


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--team", required=True, choices=TEAM_IDS)
    parser.add_argument("--cases", required=True, type=Path)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--report", type=Path,
        help="results.json from a complete successful run of these five cases")
    source.add_argument("--witnesses", type=Path,
        help="an existing witnesses.json instead of a recorded run")
    parser.add_argument("--output", type=Path, default=ROOT / "submissions/cases.zip")
    args = parser.parse_args(argv)
    try:
        cases = read_json(args.cases)
        if args.report is not None:
            # Reports can include full request traces and exceed the case-file
            # size limit. Read them as data only; never import or execute them.
            if args.report.is_symlink() or not args.report.is_file():
                raise ValueError("Provide an ordinary results.json file.")
            report = json.loads(args.report.read_text(encoding="utf-8"))
            witnesses = witnesses_from_report(args.team, cases, report)
        else:
            witnesses = read_json(args.witnesses)
        pack = write_pack(args.output, cases, witnesses, args.team)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    print(args.output)
    print("Included: five declarative cases, replayable witnesses and the generated CASE_MANIFEST.json.")
    print("Submit this ZIP together with the source ZIP from submit.py at every grading submission.")
    print("Case content hash:", pack["manifest"]["content_hash"])
    print("Five witnesses replayed successfully; zero API calls. Semantic review remains separate.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
