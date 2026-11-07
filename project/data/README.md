# Public data and case inspection

The repository supplies **nine Dev cases and 30 fixed Public cases**: three and
ten per difficulty, respectively. These support local development. This page and
the full JSON examples are optional inspection references. See the
[benchmark guide](../BENCHMARK.md#shared-cases-and-evaluation) for the official
evaluation set.

## Files

| File | Contents |
|---|---|
| [`dev.json`](dev.json) | Nine complete Dev case definitions. |
| [`public.json`](public.json) | Thirty fixed Public case definitions. |
| [`catalog.jsonl`](catalog.jsonl) | Dev/Public case IDs, difficulty, initial requests and source titles. |
| [`examples.md`](examples.md) | Optional full observations and search results for each difficulty. |
| [`templates/`](templates/) | One editable case template and witness example per difficulty. |
| [`MANIFEST.json`](MANIFEST.json) | Data version and checksums. |

Complete definitions and templates contain future events and executable
conditions. Use them to inspect or create tests, never as runtime solver inputs
or case-ID answer tables. During a trip, the solver uses current observations and
returned tool replies.

## Inspect without model calls

Run from `project/`:

```bash
python inspect_case.py --split dev
python inspect_case.py --split public --tier forecast --case 1 --output runs/preview_01
```

The first command lists cases. The second reads current sources and searches
available offers in a fresh world, writing `preview.md` and `preview.json`.
A row number starts at 1 in the selected split/tier; a case ID also works. Reads
advance virtual time. Inspection requires no API key, makes no model calls or
bookings, and provides no performance score. A later solver run starts fresh.

## Make a local test or a five-case submission

For one optional local test:

```bash
python inspect_case.py --split dev --case 1 --export-case local_cases/example.json
python run.py --local-cases local_cases/example.json --output runs/local_01
```

For your five-case contribution, follow [the case guide](../CASE_GUIDE.md):
copy templates into assigned slots, edit coherent conditions, run the cases,
then package them from the successful report. The local runner accepts complete
case lists or `{slot_id, case}` entries. Keep your case files and witnesses out
of public repositories; email the case ZIP together with your solver ZIP to the
existing course submission address.

Dev and custom runs report outcome /90 and API usage. A complete Public run
evaluates 30 cases twice and shows a local development score. Only official
grading contributes to the leaderboard.
