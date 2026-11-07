# Benchmark guide: what to build and how to test it

Build an assistant that interprets current travel conditions, makes approved
bookings, prepares for announced possibilities, and verifies the trip through
handoff. Ordinary Python planning, model calls, or a combination are allowed.
There is no required LLM call count, agent count or architecture bonus.

This project uses **`travel-2026f-v10`** with operational spending, arrival and
refund contracts. Read linked conditions as part of the task. The familiar
transport tools and the 90 outcome + 10 API-efficiency rubric remain in use.

## Shared cases and evaluation

| Set | Distinct cases | Use |
|---|---:|---|
| Dev | 9: three per difficulty | Start, debug and compare small changes. |
| Fixed Public | 30: ten per difficulty | Published development examples; two repeats give a local /100 score. |
| Team-contributed | 30: ten per difficulty | Five per team; each team knows its own cases, but others do not receive them. |
| Independent Hidden | 60: twenty per difficulty | Unreleased cases prepared within the published scope below. |

Official leaderboard and final grades use the same **120 cases once each**:
30 Public + 30 team-contributed + 60 independent Hidden. Every team gets separate
worlds with the same tools and conditions. A local Public score is for development;
it is not an official leaderboard entry.

Team contributions replace the starting cases in their assigned slots. They do
not change the fixed Public set, accumulate with repeated submissions, or require
a corresponding Hidden revision. See [CASE_GUIDE.md](CASE_GUIDE.md) for the five
slots, the December 7 case-content cutoff, and the two required submission ZIPs.

Unreleased cases may use new wording, values and combinations of the supported
conditions. They need not be variations of a Public example. All needed facts
are available through initial observations, discoverable sources or arrived
updates; there are no secret scoring rules or unannounced tool capabilities.
The supported condition scope closes with the December 7 cutoff. A later common
selection, including the final evaluation, stays within that scope. Necessary
correctness repairs are explained and applied consistently. Scores from different
evaluation-set versions are not mixed.

## What changes across the difficulties?

| Difficulty | Main work |
|---|---|
| Basic | Interpret current scope, spending and required arrival; book a suitable trip, remove the hotel fee and verify the result. |
| Reactive | Meet the announced first-booking obligation, then apply partial amendments and repair the trip under its purchased refund terms. |
| Forecast | Prepare while a disruption is uncertain, account for reservation deposits, and act on the actual operating report when it arrives. |

Use each observation's `booking_deadline`, `handoff_minute` and `horizon` and read
the corresponding request. The supplied operational examples require a first
confirmation by minute 12; Basic hands off from minute 12, while advanced examples
monitor through minute 28. The common horizon is minute 36. Announced deadlines
and sale windows can vary within the supported case bounds; do not infer them
from a case ID or difficulty name.

## Read the contracts, then calculate

Current observations link the spending and arrival sources. Search offers link
their refund source and version. Numeric fare fields describe ordinary base
terms; a linked conditional refund clause can override them. The supplied
controller can consume interpreted expressions and perform ordinary arithmetic.
Students may keep it or implement their own planning loop in `solution/policy.py`.

When an approval compares available quotes, the evaluation includes unheld
on-sale inventory and the candidate's own valid held quote. It does not add
every other held ticket to that quote set. A condition about a live backup uses
the separate set of live holds. A held quote can remain usable after public
sales close, until the hold itself expires.

| Condition | What the assistant must distinguish |
|---|---|
| Spending authority | A total ceiling from remaining money; current approval from a conditional future allowance; one trip or mode from another. |
| Required arrival | Client-site arrival after transfer from terminal arrival, meeting start, optional lunch or a spending incentive. |
| Cancellation | Retained dollars from refunded dollars; a purchased contract version from a later amendment; a quote from an actual live hold. |
| Reservation deposit | A charge made now from a future ticket payment; the credited deposit from an unused deposit that remains spent. |
| Changed evidence | An arrived amendment from an announced possibility; updated fields from unrelated conditions that continue. |

### Spending permission applies when a charge completes

A supplied Basic source allows USD 145 total when the ticket is flight and
USD 105 for another mode. Another permits a higher total only when the preferred
fare is within USD 20 of the cheapest currently offered ticket that reaches the
client by 10:55. A cheaper late ticket is not the comparison fare.

A Forecast example starts with USD 145 and allows USD 190 only after an actual
flight delay of at least 30 minutes is observed. A warning alone does not activate
that allowance. These are alternative total ceilings, not amounts to add.
Include retained charges, deposits still spent and any hotel charge still due.
A later lower allowance does not revoke an earlier authorized purchase, but it
does constrain new charged actions.

### Arrival can be earlier than the meeting

One supplied source has a meeting at 11:15 but requires registration by 09:40.
The client arrival must meet 09:40 after adding the transfer. Another source
allows extra spending for an optional arrival by 09:30 while the binding arrival
deadline remains 10:55. The incentive does not itself create an earlier deadline.

### A refund can depend on time and a real reservation

Examples include a full refund if cancellation completes by minute 23, or only
while an unexpired replacement costing at most USD 190 and reaching the client
by 09:50 is held. A search result does not satisfy the latter condition. Other
terms combine an observed delay, a cancellation cutoff and a live replacement.

Refund terms freeze when a ticket is confirmed; their conditions are evaluated
when cancellation completes. A later source version applies to later purchases.
Compare the retained charge plus replacement cost before cancelling. The normal
`locked`, `fee` and `flexible` fields remain base terms; use the applicable linked
contract for an exception.

### A backup hold can cost money before the outcome is known

A supplied weather example announces a possible delay, a final operating notice
at minute 18, and recovery sales closing at minute 14. Each recovery hold charges
USD 20 immediately. If confirmed, that USD 20 is credited toward the quoted fare;
if unused, it remains spent. A hold does not activate conditional emergency funds.

Prepare only when the current allowance covers the deposit. Leave enough time
for source reads, cancellation and confirmation before the hold expires. An
observed delay is already reflected in current search/booking arrivals; do not
add it twice. A false alarm can leave the original ticket suitable and the unused
deposit as a real expense. A sound hedge does not need to predict the future.

These are examples from the public material, not mandatory action sequences.
Every valid plan receives the same outcome checks.

## Supported condition combinations

Public, team-contributed and Hidden cases may combine the capabilities below.
The operational conditions produce three results: a total spending ceiling, a required client-arrival time,
and the dollars retained on cancellation. Cancellation may also be forbidden.
No new tool or scoring criterion is added.

### Basic: combine conditions in a stable trip

- Apply a default rule, an exception, and a more specific exception when their
  conditions hold. A spending rule and an arrival rule may share a definition.
- Find eligible comparison offers using mode, carrier, fare, accessibility and
  client arrival. A rule may use the lowest fare or earliest arrival in that
  set, add a stated margin, apply a cap, or give a fallback when the set is empty.
- Keep the selected ticket separate from the comparison set. For example, a
  rail quote may set the spending limit without requiring the traveler to choose
  rail. Read which restriction applies to which ticket.
- Distinguish the hotel waiver from earlier retained charges. Both are observed
  financial facts, but they can activate different conditions. Client-arrival
  time includes the transfer; virtual time tells when a tool action completes.
- A premium for a selected mode may depend on a reference fare defined in a
  linked source, the selected offer's own deposit, and the total deposits already
  paid but not yet credited. A requested hotel waiver is not a completed waiver.

### Reactive: apply updates without losing the purchased terms

- A spending supplement may depend on the absence of an eligible timely
  alternative, the selected mode or accessibility, arrival, and earlier retained
  charges. Check the whole condition before making a new charged action.
- One arrived update can change arrival while a later update changes spending.
  Keep requirements that were not replaced. A later lower allowance constrains
  new charges; it does not revoke an earlier authorized purchase.
- Refund terms belong to the version purchased. Their conditions can refer to
  that purchase time, the actual cancellation time and a live replacement hold.
  Cancellation may require a qualifying held service different from the ticket
  being cancelled.
- Recovery sales may open later. Use an opening time from an arrived notice,
  and leave time for the required reads, holds and other tool actions.
- A live replacement hold can change the refund on cancellation. A later
  spending supplement can then depend on the refund actually credited and the
  charges permanently retained. Apply its mode and other restrictions too;
  a promised refund does not count as money already returned.

### Forecast: prepare for several possible outcomes

- The same initial warning can lead to a harmless outcome or a delay requiring
  recovery. Conditions about a real disruption use the actual operating report,
  together with any stated time boundary. A warning alone does not activate them.
- Recovery sales can close before the report. A paid hold may preserve an option,
  but its deposit must fit current authority. An expired hold's lost deposit is
  different from the deposit attached to a live hold.
- A definition such as an eligible, timely, sheltered service may be reused
  across spending, arrival and refund sources. Apply the same definition in each
  place instead of independently guessing what it means.
- Rules may combine a capped comparison fare and an empty-set fallback, a
  mode-specific arrival extension, ordinary retained fees, partial relief, a
  full refund, or cancellation allowed only with a qualifying live replacement.
  An affordable preparation that works across outcomes remains a valid choice.
- Actual disruptions to two modes can jointly determine the approved recovery
  mode. A shared definition may govern both spending and refund terms. Paid
  deposits that have not yet been credited can reduce a stated cancellation
  charge, down to an explicit zero minimum. Several affordable backup holds
  may be useful before the operating outcomes are known.

These are supported capabilities, not a required plan or an answer for a case.
Read the actual conditions and their scope through the normal tools. Public
examples need not show every allowed combination. When writing or testing a new
case, keep the prose, executable conditions and information timing consistent.

## Time, source access and reliable actions

Clock times and virtual minutes are different. A terminal arrival of 09:10 plus
a 35-minute transfer means client arrival at 09:45. Tool time starts at virtual
minute 0; model calls and local computation do not advance it. Up to three tools
can run concurrently. Events at an action's completion time apply before that
action completes.

A `read` source must be in the catalog when its batch is submitted. Complete the
`hotel-terms` read before requesting its linked bulletin in a later batch. A
rejected read still consumes its normal duration. Keep exact consent/evidence
codes and source versions; claim the hotel waiver strictly before its cutoff.

Sale and hold expiry are strict: completing at expiry is too late. Inspect the
returned hold expiry instead of assuming a duration. Cancel an existing
replacement before confirming another. Outbound consent does not authorize
changing the hotel or the colleague's return.

After a lost confirmation reply, check `status` with the original request key.
The booking may already exist. Reusing the same key and payload is idempotent;
a new key can create a duplicate. Verify the final commitment and continue through
the required handoff. An actual model API timeout is separate: its unknown usage
cannot be treated as a free completed run.

## Scores and useful tests

The rubric remains usable arrival 40, current requests 20, hotel waiver 10,
safety 10, reliable handoff 10, and one shared API-efficiency term up to 10.
The four request checks divide those 20 points: budget, feasible mode preference,
accessibility and carrier eligibility. Basic /30 + Reactive /30 + Forecast /30
+ efficiency /10 is another breakdown of the same total.

Initial-service credit records a confirmed ticket by the initial deadline;
arrival and current-request checks assess the final trip. A confirmation alone
does not prove that the ticket satisfied the request when it was first bought.
Travel spending is an authorization constraint, not an extra cheapest-ticket
score. A valid conservative plan can earn full outcome credit.

The [student guide](README.md#7-understand-the-100-point-score) gives the exact
cost formula and allowances. Only official evaluation costs enter the official
score. Public exposure and self-authored cases can lead to overfitting; compare
performance on held-back local examples too.

When testing a change, keep the solver fixed and inspect actual traces as well
as the aggregate score. Useful tests include:

- Keep some combinations aside while developing; test them only after freezing your current solver.
- Reword an instruction without changing its facts, then inspect the interpreted condition.
- Change an amount, mode, carrier or offer order without making an ID the answer.
- Test both sides of a refund cutoff, including the duration of cancellation.
- Change a purchased refund source later and check which contract version applies.
- Compare a paid backup hold with waiting; include an unused-deposit outcome.
- Keep the initial weather warning identical, then vary the actual operating outcome.
- Combine a spending exception, a refund prerequisite and an arrived amendment; check that each applies to the correct action and source version.
- Amend one field while preserving the other requirements.
- Check an interrupted confirmation and preserve both protected bookings.

## Make your own local tests

Run from `project/` to copy one existing public example:

```bash
python inspect_case.py --split dev --case 1 --export-case local_cases/example.json
python inspect_case.py --local-cases local_cases/example.json --case 1
python run.py --local-cases local_cases/example.json --output runs/local_01
```

For the five assigned case slots, follow the complete workflow in
[CASE_GUIDE.md](CASE_GUIDE.md). Case definitions contain authoring programs and
future events; they must never enter runtime solver inputs. A solver uses only
arrived observations and tool replies, without looking up plans by case ID.

Validation checks supported structure. Successful witness replay demonstrates a
feasible sequence, but neither proves prose/rule equivalence or that decisions
used only then-available information. Those points need review. Report local
failures honestly; do not present fixtures or replayed actions as new model runs.
