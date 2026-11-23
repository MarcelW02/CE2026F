"""Build stress_v6: case settings that never vary in the other banks, plus unusual scenarios. Local diagnosis only.

Run from project/:  .venv/Scripts/python.exe -I ../tools/stress_builder_v6.py  (writes local_cases/stress_v6.json)

A coverage audit of the 117 local cases showed identical transfers for every mode, almost only "fee" fares,
step-free always required, the first booking always due at minute 12, 16-minute holds and one evidence type.
This bank varies exactly those settings (S) and adds unusual situations (U): a preference that becomes
affordable later, a distracting message, a terminal-arrival deadline, a per-ticket price cap, a revised weather
report, an amendment at minute 1, an interrupted reply with an early event, and a locked fare under a forecast.
Truth fields, documents, fare lines and the contract change together; every case is validated and checked.
"""
import copy
import json
import sys
from pathlib import Path

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT))
from framework.world_factory import validate_case, world_for_case  # noqa: E402

DEV = {c["case_id"]: c for c in json.loads((ROOT / "data/dev.json").read_text(encoding="utf-8"))}
ORDINARY = "ordinary cancellation retains USD 65; there is no additional exception."


def base(source_id, new_id, **fields):
    c = copy.deepcopy(DEV[source_id])
    c["case_id"] = new_id
    c.update(fields)
    return c


def add_event(c, at, kind, text, **changes):
    c["events"].append(dict(at=at, kind=kind, text=text, changes=changes))
    c["events"].sort(key=lambda event: event["at"])


def set_ticket_line(c, identifier, clause):
    fare = c["documents"]["fare-contract"]
    fare["text"] = "\n".join(f"Ticket {identifier}: {clause}" if line.startswith(f"Ticket {identifier}:") else line
                             for line in fare["text"].split("\n"))


def add_offer(c, identifier, **fields):
    offer = copy.deepcopy(c["options"][0])
    offer.update(id=identifier, hold_fee_usd=0, weather_exposed=False, available_from=0, expires_at=36, inventory=2,
                 change_policy="fee", cancel_fee_usd=65, step_free=True)
    offer.update(fields)
    c["options"].append(offer)
    c["operational_sources"]["refund_terms"][identifier] = "fare-contract"
    c["operational_contract"]["refund_terms"][identifier] = 65
    c["documents"]["fare-contract"]["text"] += f"\nTicket {identifier}: {ORDINARY}"


def set_preference(c, mode):
    old = c["preferred"]
    c["preferred"] = mode
    c["initial_request"] = c["initial_request"].replace(f"Prefer {old} whenever a suitable {old} is affordable",
                                                        f"Prefer {mode} whenever a suitable {mode} is affordable")
    profile = c["documents"]["traveler-profile"]
    profile["text"] = profile["text"].replace(f"Use a suitable {old} if one is affordable", f"Use a suitable {mode} if one is affordable")


def per_mode_transfer(c, flight, train, coach):
    c["transfer"] = dict(flight=flight, train=train, coach=coach)
    c["documents"]["transport-guide"]["text"] = (
        f"Weekday client transfers: flight {flight} minutes, train {train} minutes, coach {coach} minutes. Add the value for "
        "the arriving mode to terminal arrival. The result is arrival at the client, not terminal arrival.")


CASES = []

# ---------------------------------------------------------------- (S) settings that never vary elsewhere
c = base("dev-486fd97b7c", "stress6-01-transfer-differs-by-mode")
per_mode_transfer(c, 30, 10, 25)  # the cheapest flight (terminal 10:30) now reaches the client at 11:00, after 10:55
CASES.append(c)

c = base("dev-0712f477b1", "stress6-02-transfer-by-mode-then-road-closure")
per_mode_transfer(c, 15, 20, 30)
add_event(c, 14, "transport_update", "A road closure lengthens the onward transfer after flight arrivals. Read the current "
                                     "transport-guide before keeping or choosing a replacement.",
          transfer=dict(flight=35, train=20, coach=30),
          document_text="Weekday client transfers after the road closure: flight 35 minutes, train 20 minutes, coach 30 minutes. "
                        "Add the value for the arriving mode to terminal arrival. The result is arrival at the client.")
CASES.append(c)

c = base("dev-0712f477b1", "stress6-03-flexible-fee-and-locked-fares")
next(o for o in c["options"] if o["id"] == "trip-9b2440d7197").update(change_policy="flexible", cancel_fee_usd=0)
next(o for o in c["options"] if o["id"] == "trip-5fcf56ff457").update(change_policy="locked")
set_ticket_line(c, "trip-9b2440d7197", "flexible fare; cancellation at any time refunds the full price.")
set_ticket_line(c, "trip-5fcf56ff457", "locked fare; it cannot be cancelled or exchanged after confirmation.")
c["operational_contract"]["refund_terms"].update({"trip-9b2440d7197": 0, "trip-5fcf56ff457": None})
CASES.append(c)

c = base("dev-486fd97b7c", "stress6-04-step-free-not-required", requires_step_free=False)
c["initial_request"] = c["initial_request"].replace("I require step-free travel.", "Stairs are fine for me.")
c["documents"]["traveler-profile"]["text"] = c["documents"]["traveler-profile"]["text"].replace(
    "Keep step-free access.", "Step-free access is not needed.")
next(o for o in c["options"] if o["id"] == "trip-5902aa58008")["step_free"] = False  # the cheapest suitable flight
CASES.append(c)

for source, new_id, minute in (("dev-2222f98c18", "stress6-05-first-booking-by-minute-9", 9),
                               ("dev-17b13a1153", "stress6-06-first-booking-by-minute-10-forecast", 10)):
    c = base(source, new_id, booking_deadline=minute)
    c["initial_request"] = c["initial_request"].replace("required by virtual minute 12", f"required by virtual minute {minute}")
    CASES.append(c)

c = base("dev-0712f477b1", "stress6-07-six-minute-holds", hold_minutes=6)
CASES.append(c)

c = base("dev-dfc8cdde33", "stress6-08-other-evidence-type", waiver_type="disruption-letter")
c["documents"]["hotel-bulletin"]["text"] = c["documents"]["hotel-bulletin"]["text"].replace("cancel-reference", "disruption-letter")
CASES.append(c)

c = base("dev-d1e8acd8cc", "stress6-09-single-seat-sold-at-minute-7")
c["events"] = []
target = next(o for o in c["options"] if o["id"] == "trip-b853cdd50b5")  # cheapest suitable coach
target["inventory"] = 1
add_event(c, 4, "stock_update", "Only one seat remains on trip-b853cdd50b5, and another buyer will take it at virtual minute 7 "
                                "unless it is held.")
add_event(c, 7, "sellout", "trip-b853cdd50b5 is now sold out to another buyer.", option_id="trip-b853cdd50b5")
CASES.append(c)

# ---------------------------------------------------------------- (U) unusual scenarios
c = base("dev-0712f477b1", "stress6-10-preferred-mode-affordable-later")
set_preference(c, "train")
add_offer(c, "trip-7a1e0c0f610", mode="train", carrier="Birch", price=170, arrival_minute=550)  # over 145, under 190
CASES.append(c)

c = base("dev-0712f477b1", "stress6-11-distracting-message")
c["events"] = []
add_event(c, 16, "user_update", "For information only: my colleague dislikes Birch and prefers Cedar, but that is about their "
                                "own return. My outbound rules, spending approval and deadline are unchanged.")
CASES.append(c)

c = base("dev-5f4a5e2291", "stress6-12-terminal-arrival-deadline")
c["documents"]["arrival-contract"]["text"] = (
    "Registration closes at 09:40 at the client. Because the transfer from the terminal takes the time listed in "
    "transport-guide, I must be at the arrival terminal by 09:20.")
CASES.append(c)

c = base("dev-486fd97b7c", "stress6-13-per-ticket-price-cap")
c["documents"]["request-contract"]["text"] = (
    "The ticket itself may cost at most USD 120. Including retained cancellation charges and the hotel charge, total "
    "additional spending may not exceed USD 145.")
c["operational_contract"]["budget_limit"] = {"op": "if", "when": {"op": "le", "left": {"var": "candidate.price"}, "right": 120},
                                              "then": 145, "else": 0}
CASES.append(c)

c = base("dev-17b13a1153", "stress6-14-weather-report-revised")
add_event(c, 22, "weather_update", "Updated operating report: the exposed flight departures are now delayed by 60 minutes. "
                                   "This replaces the earlier realized delay.",
          weather_delays={"flight": 60}, forecast_version=4,
          forecast_text="Updated operating outcome at minute 22: flight delay 60 minutes. Recovery departures listed as "
                        "unexposed retain their original arrival times.")
CASES.append(c)

c = base("dev-0712f477b1", "stress6-15-amendment-at-minute-1")
c["events"][0]["at"] = 1
CASES.append(c)

c = base("dev-2222f98c18", "stress6-16-interrupted-reply-and-early-amendment", interrupt_confirmation=True)
c["events"][0]["at"] = 8
CASES.append(c)

c = base("dev-17b13a1153", "stress6-17-locked-exposed-flight-under-forecast")
next(o for o in c["options"] if o["id"] == "trip-19702928b71").update(change_policy="locked")  # cheapest exposed flight
set_ticket_line(c, "trip-19702928b71", "locked fare; it cannot be cancelled or exchanged after confirmation.")
c["operational_contract"]["refund_terms"]["trip-19702928b71"] = None
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
            if not feasible and at <= case["booking_deadline"]:
                problems += 1
        print(f"{case['case_id']:48} {' '.join(report)}")
    out = ROOT / "local_cases" / "stress_v6.json"
    out.write_text(json.dumps(CASES, indent=1, ensure_ascii=True), encoding="utf-8")
    print(f"\nwrote {len(CASES)} cases to {out}; problems={problems}")


if __name__ == "__main__":
    main()
