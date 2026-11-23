"""Build stress_v4: planner situations not covered by stress_v1-v3, for local diagnosis only.

Run from project/:  .venv/Scripts/python.exe -I ../tools/stress_builder_v4.py  (writes local_cases/stress_v4.json)

Mid-trip preference and accessibility changes, a preferred offer that opens later, a budget cut for new
commitments, short holds, an early waiver deadline, several events in one minute and two deadline changes.
Each case keeps its template's wording style; changed rules are stated in the documents and events, the case
fields and contract truth are updated to match, and every case is validated and checked for feasible offers.
"""
import copy
import json
import sys
from pathlib import Path

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT))
from framework.world_factory import validate_case, world_for_case  # noqa: E402

DEV = {c["case_id"]: c for c in json.loads((ROOT / "data/dev.json").read_text(encoding="utf-8"))}


def base(source_id, new_id, **fields):
    c = copy.deepcopy(DEV[source_id])
    c["case_id"] = new_id
    c.update(fields)
    return c


def add_event(c, at, kind, text, **changes):
    c["events"].append(dict(at=at, kind=kind, text=text, changes=changes))
    c["events"].sort(key=lambda event: event["at"])


def add_offer(c, identifier, **fields):
    """A new offer with ordinary fee terms, listed in the fare contract and the refund truth."""
    offer = copy.deepcopy(c["options"][0])
    offer.update(id=identifier, hold_fee_usd=0, weather_exposed=False, available_from=0, expires_at=36,
                 inventory=2, change_policy="fee", cancel_fee_usd=65, step_free=True)
    offer.update(fields)
    c["options"].append(offer)
    fare_id = next(iter(set(c["operational_sources"]["refund_terms"].values())))
    c["operational_sources"]["refund_terms"][identifier] = fare_id
    c["operational_contract"]["refund_terms"][identifier] = 65
    c["documents"][fare_id]["text"] += f"\nTicket {identifier}: ordinary cancellation retains USD 65; there is no additional exception."


def set_preference(c, mode):
    old = c["preferred"]
    c["preferred"] = mode
    c["initial_request"] = c["initial_request"].replace(f"Prefer {old} whenever a suitable {old} is affordable",
                                                        f"Prefer {mode} whenever a suitable {mode} is affordable")
    profile = c["documents"]["traveler-profile"]
    profile["text"] = profile["text"].replace(f"Use a suitable {old} if one is affordable", f"Use a suitable {mode} if one is affordable")


def amendment(c, at, text, docs, truth):
    """A user update that revises operational documents (version + 1) and the contract truth."""
    revised = []
    for doc_id, doc_text in docs.items():
        current = max([c["documents"][doc_id]["version"]] + [d["version"] for e in c["events"]
                       for d in e["changes"].get("operational_documents", []) if d["id"] == doc_id])
        revised.append(dict(c["documents"][doc_id], text=doc_text, version=current + 1))
    add_event(c, at, "user_update", text, operational_contract=truth, operational_documents=revised)


CASES = []

# 01 Mid-trip preference switch, with a suitable coach on sale (template prefers flight).
c = base("dev-0712f477b1", "stress4-01-preference-switch-to-coach")
c["events"] = []
add_offer(c, "trip-c0ac4b0a101", mode="coach", carrier="Birch", price=100, arrival_minute=630)
add_event(c, 16, "user_update", "For this journey only I now prefer coach whenever a suitable coach is affordable. Exchange the "
                                "replacement if a feasible coach exists. All other conditions stay as they are.", preferred="coach")
CASES.append(c)

# 02 The preferred mode only goes on sale later (template prefers flight; this case prefers train).
c = base("dev-0712f477b1", "stress4-02-preferred-offer-opens-later")
c["events"] = []
set_preference(c, "train")
add_offer(c, "trip-7a1e0b5e202", mode="train", carrier="Birch", price=115, arrival_minute=620, available_from=16)
add_event(c, 16, "stock_update", "A new train departure is now on sale. Search the current offers.")
CASES.append(c)

# 03 Budget cut for new commitments only; the paid booking stays authorized.
c = base("dev-0712f477b1", "stress4-03-budget-cut-for-new-commitments")
c["events"] = []
amendment(c, 16, "Finance has reduced my spending approval for any new commitment; read the revised approval. Already "
                 "confirmed charges stay approved.",
          {"request-contract": "For any new commitment, total additional spending may not exceed USD 100. Charges already "
                               "confirmed under the earlier approval remain authorized. Include retained cancellation charges "
                               "and any hotel fee."},
          {"budget_limit": 100})
CASES.append(c)

# 04 Short holds: a hold lasts 5 minutes.
CASES.append(base("dev-2222f98c18", "stress4-04-short-holds", hold_minutes=5))

# 05 Early waiver deadline (minute 8), Forecast and Reactive.
for source, new_id in (("dev-17b13a1153", "stress4-05-early-waiver-deadline-forecast"),
                       ("dev-0712f477b1", "stress4-06-early-waiver-deadline-reactive")):
    c = base(source, new_id, waiver_deadline=8)
    bulletin = c["documents"]["hotel-bulletin"]
    bulletin["text"] = bulletin["text"].replace("before virtual minute 30", "before virtual minute 8")
    CASES.append(c)

# 07 Three events in the same minute: the amendment, a transfer change and a provider notice.
c = base("dev-0712f477b1", "stress4-07-three-events-same-minute")
add_event(c, 16, "transport_update", "A road closure lengthens the onward transfer for flight arrivals. Read the current "
                                     "transport-guide.",
          transfer=dict(flight=25, train=20, coach=20),
          document_text="Add 25 minutes to terminal arrival for a flight and 20 minutes for a train or coach. The result is "
                        "arrival at the client, not terminal arrival.")
add_event(c, 16, "provider_notice", "Provider notice: confirmation replies may be slow today. Check a booking's status with "
                                    "the same request key before trying another commitment.")
CASES.append(c)

# 08 Two deadline changes: earlier at 16 (template amendment), then later again at 22.
c = base("dev-0712f477b1", "stress4-08-deadline-earlier-then-later")
amendment(c, 22, "The client has moved the appointment back; read the updated arrival obligation. Spending stays as last "
                 "approved.",
          {"arrival-contract": "Reach the client by 10:50 including the current transfer. This replaces the 09:50 deadline. "
                               "Keep step-free access and all other current outbound conditions."},
          {"arrival_deadline": 650})
CASES.append(c)

# 09 Step-free access becomes required mid-trip; the cheapest flight is not step-free.
c = base("dev-0712f477b1", "stress4-09-step-free-required-midtrip", requires_step_free=False)
c["events"] = []
c["initial_request"] = c["initial_request"].replace("I require step-free travel.", "Stairs are fine for me today.")
profile = c["documents"]["traveler-profile"]
profile["text"] = profile["text"].replace("Keep step-free access.", "Step-free access is not needed for now.")
next(o for o in c["options"] if o["id"] == "trip-9b2440d7197")["step_free"] = False
add_event(c, 16, "user_update", "I now need step-free access for my outbound, including any ticket already booked. Exchange "
                                "it if needed. All other conditions continue.", requires_step_free=True)
CASES.append(c)


def feasible_offers(case, at):
    world = world_for_case(copy.deepcopy(case), concurrency=3)
    world._advance(at)
    found = []
    for option in world._options.values():
        on_sale = option["inventory"] > 0 and option.get("available_from", 0) <= world.now < option["expires_at"]
        rules = world._rules
        if (on_sale and option["price"] <= world._limit(option)
                and world._offer_facts(option)["meeting_arrival"] <= world._deadline(option)
                and (not rules["requires_step_free"] or option["step_free"]) and option["carrier"] not in rules["avoid_carriers"]):
            found.append(f"{option['id'][-4:]}:{option['mode'][0]}{option['price']}")
    return sorted(found)


def main():
    problems = 0
    for case in CASES:
        validate_case(case)
        report = []
        for at in sorted({0, *[e["at"] + 1 for e in case["events"]]}):
            feasible = feasible_offers(case, at)
            report.append(f"t{at}:[{' '.join(feasible)}]")
            if not feasible and at <= 12:
                problems += 1
        print(f"{case['case_id']:44} pref={case['preferred']:6} {' '.join(report)}")
    out = ROOT / "local_cases" / "stress_v4.json"
    out.write_text(json.dumps(CASES, indent=1, ensure_ascii=True), encoding="utf-8")
    print(f"\nwrote {len(CASES)} cases to {out}; problems={problems}")


if __name__ == "__main__":
    main()
