# CE2026F Final Project

## Travel planning with dynamic replanning

Build a travel assistant that keeps a trip workable while requests, travel
conditions and booking opportunities change. Your system must interpret the
current evidence, maintain useful state, make approved bookings, and verify the
result. The final score combines task outcomes and API efficiency, out of 100.

**Final submission: December 21, 2026 (KST).** The exact deadline time will be
announced separately.

**All final presentations are online via Zoom.** No on-site attendance is required.
See the [October 22 project updates](#project-updates) for presentation details
and answers about models, hidden cases, implementation and evaluation.

**Start in [`project/`](project/).** It contains the complete runnable starter,
public data, tools and evaluator. Install the listed dependencies and follow
the setup steps below to run it.

## Get started

Clone this repository, open a terminal in the cloned folder, and run:

```bash
cd project
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Use Python 3.11 or later. On Windows, activate with
`.venv\Scripts\activate`; in PowerShell, use
`.venv\Scripts\Activate.ps1` and `Copy-Item .env.example .env`.
Open `.env` locally and replace the placeholder with your own course API key,
which has already been distributed to you:

```dotenv
OPENAI_API_KEY=PASTE_YOUR_KEY_HERE
```

Then check the setup without model calls, followed by a small paid run:

```bash
python run.py --offline
python inspect_case.py --split dev --case 1
python run.py --split dev --limit 2 --output runs/setup_check
```

The first two commands need no key and make no model calls. The inspection
shows a real request, current sources and travel offers. The last command makes
paid requests. Use a fresh output directory for each run. Open
`runs/setup_check/report.html` to inspect what happened.

## Your implementation

Edit exactly these three files:

You may change any of them; you do not have to change all three.

| File | Your choices |
|---|---|
| [`project/solution/config.py`](project/solution/config.py) | Model, supported settings, architecture, refresh and policy budgets. |
| [`project/solution/prompts.py`](project/solution/prompts.py) | Task instructions and role prompts. |
| [`project/solution/policy.py`](project/solution/policy.py) | Routing, context selection, memory, local planning and the agent loop. |

The starter already runs. You can improve the supplied loop or implement your
own loop inside `policy.py`; a new memory class or a full rewrite is optional.
Keep submitted helper code in these three files. Use the Python standard library,
the supplied framework and packages in `requirements.txt`; extra packages and
local assets are not included or installed from your submission. Keep the shared
framework, cases, accounting, evaluator and runners unchanged.

A useful first experiment is to enable selective context refresh on a Reactive
dev case and compare the outcome and both model-cost estimates. The
[student guide](project/README.md#6-improve-with-visible-experiments) gives the
commands. Local optimization and valid symbolic solutions are allowed. Agent
count itself earns no points.

Read the **[student guide](project/README.md)** for the scenario, tool contracts,
memory scaffold, evaluation, debugging and submission steps.

## Test and submit

Run these commands from `project/`:

```bash
python run.py --split dev --output runs/dev_01
python run.py --split public --output runs/public_01
python submit.py --output submissions/team_solution.zip
```

Start with nine dev cases. Read the [benchmark guide](project/BENCHMARK.md)
to understand the kinds of problems your assistant must handle and how to make
your own optional local tests. The supplied data contains 33 student-visible
cases: nine dev and 24 public. Local tests and dev runs report outcomes out of 90,
grading cost and estimated API cost. Grading charges cached input at the regular
input rate so a cache discount does not change your score.

Public evaluation runs 24 cases twice and gives a provisional public score.
Final grading reruns the frozen submitted source on 24 public plus 24 hidden
cases, twice each: 96 episodes. Submit only the generated source ZIP, containing
your three solution files and an automatic manifest. Your local test data is not
part of the submission or official grading.

Never put a real key in source, commit `.env`, or include it in a submission.
The repository ignores local keys, environments, runs, local test cases and
submission ZIPs. `.env.example` contains only a placeholder.

## Project materials

- [Student guide](project/README.md)
- [Benchmark characteristics and local test authoring](project/BENCHMARK.md)
- [Public data and case inspection](project/data/README.md)
- [Worked scenario examples](project/data/examples.md)
- [Public tools and implementation](project/framework/)

The data guide explains zero-API inspection. All 33 student-visible cases have
initial requests and source titles in
[`project/data/catalog.jsonl`](project/data/catalog.jsonl). The benchmark guide
explains what can vary, how to test new wording or trip facts, and how to avoid
building a solution that only recognizes known case IDs.

Course staff will publish interim results in a shared Google spreadsheet.
The leaderboard will be created later, and its link will be added here.
It will show total /100, each criterion, Basic /30, Reactive /30, Forecast /30,
the shared API-efficiency score /10, full success, grading cost and estimated API
cost. The three difficulty contributions plus efficiency add to the total.
Detailed per-tier outcomes use the same 90-point outcome rubric.

**Final project submission is due December 21, 2026 (KST).** The exact deadline
time and submission channel will be announced separately. The interim leaderboard
schedule uses Korean calendar dates (Asia/Seoul):

| Dates in 2026 | Interim grading requests per team |
|---|---|
| Through December 13 | One per calendar day. |
| December 14–19, inclusive | No daily limit. |
| From December 20 | Closed. |

The December 20 cutoff closes interim feedback; the final source ZIP is still due
on December 21. The spreadsheet link will be added here after the leaderboard is
created. Final grades use the frozen submission's task results and grading cost,
not leaderboard rank.

`CE2026F_A3_Documents.zip` is the existing Assignment 3 document collection.
It is independent of this final project and is not needed by the travel simulator.

## Project updates

October 22, 2026.

**Latest October 22 update: Decisions and `gpt-6-luna` are now supported.**
Refresh your project from the updated release before using them; keep the shared
framework unchanged. Use your own previously issued course API key. The default
starter remains `gpt-5.6-luna`, and both new options are optional. This update
supersedes the earlier guidance that excluded Decisions and Luna 6.0.

These clarifications explain the project contract and the presentation format.
They add no required implementation or grading criterion. See the
[student guide](project/README.md) for setup, tools, scoring and submission.

**Final presentations are online via Zoom for all teams.** There are no onsite
presentations. Follow the course schedule for your presentation date and session;
the Zoom link and joining details will be announced later. The final source ZIP
is due **December 21, 2026 (KST)**. Its exact deadline time and submission channel
will be announced separately. December 21 is the source-submission deadline,
not an announcement of the presentation date.

- **Allowed models and API.** Responses requests through `api.json` accept
  `gpt-6-luna`, `gpt-5.6-luna`, `gpt-5.4-nano`, `gpt-5-mini`, `gpt-5-nano` and
  `gpt-4o-mini`. Decisions requests through `api.decide` use `gpt-6-luna` and
  return `choice`, `predicate` or `score` answers. Use each endpoint's documented
  controls; Decisions does not take Responses effort or sampling settings. Both
  methods share the call/dollar guards and usage ledger. Do not create a separate
  client, edit protected framework files, or add automatic retries or fallback.
  The [student guide](project/README.md#4-use-the-supplied-tools-and-api) shows
  the wrapper and an optional example. A model's confidence is not proof that a
  choice is correct, so keep normal booking and status verification.

- **Hidden cases and parsing.** Hidden evaluation follows the published tools,
  schemas and grading criteria, but is not limited to rewording public cases.
  Amounts, requirements, combinations and event timings can vary within that
  contract. Use source catalogs, document links and tool replies. Treat offer
  IDs, booking IDs, approval codes and evidence codes as exact observed strings;
  do not assume a fixed prefix, number of digits or length. General local parsers
  are allowed. Future event definitions and case-ID answer tables cannot guide
  solver actions. There is no extra hidden criterion.

- **Architecture and memory.** You may keep the starter, use one or several model
  roles, or build a general symbolic policy. There is no agent-count bonus.
  Improve observed behavior and cost. Submit only `solution/config.py`,
  `solution/prompts.py` and `solution/policy.py`, packaged with `submit.py`.
  Helpers stay inside those files, and travel actions use the supplied world
  interface. A custom memory design or full loop rewrite is optional.

- **What the score measures.** Evaluation checks booking state **and action
  history**. A suitable final booking does not erase missed initial-booking
  deadlines, duplicates or unsafe changes. Outcomes contribute up to 90 points,
  with up to 10 more for API efficiency. Grading cost charges all input tokens,
  including cached input, at the regular input rate. Responses also counts output
  at its output rate; Decisions has no output fee. The separate API cost estimate
  remains visible.
  Cache discounts do not improve the grade. API efficiency reaches its maximum
  at or below the fixed benchmark cost; further savings do not add points.
  Valid within-budget travel plans receive the same budget credit even if their
  fares differ. See the [scoring explanation](project/README.md#7-understand-the-100-point-score)
  for the formula and both cost views.

- **Repair and API interruptions.** A bounded content-repair loop may make extra
  `api.json` or `api.decide` requests to correct a content mistake; every request
  counts toward the existing limits and cost. Actual API timeouts, connection,
  authentication or rate-limit failures are different: stop the run, preserve
  partial records and resolve the cause before a fresh run. No automatic paid
  retry or engine fallback is provided. A simulated missing booking reply uses
  the original request key and `status` to check whether the booking committed.

- **Development checks.** Improve on dev and optional local cases, then test the
  same frozen source and settings on cases kept aside during tuning. Keep local
  case text, fields and event effects consistent. An old result is evidence for
  the code that produced it, not for later edits. Compare difficulty-level
  outcomes, failures and grading cost. Public and self-authored cases can be
  overfit; small checks do not prove broad generalization. Final grading reruns
  the frozen source on the published public-plus-hidden protocol.
