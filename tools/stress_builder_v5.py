"""Build stress_v5: fallback triggers, case size and rule types absent from Public/Dev, for local diagnosis only.

Run from project/:  .venv/Scripts/python.exe -I ../tools/stress_builder_v5.py  (writes local_cases/stress_v5.json)

The 2026-11-23 leaderboard showed that hidden cases mostly reach the full interpreter call, which the
earlier banks rarely trigger. This bank adds (T) plausible full-path triggers, (S) larger cases with up to
20 offers, long documents and many sources, and (R) rule types Public never uses: locked fares, refunds by
carrier and two simultaneous forecasts. Truth fields, documents, fare lines and the contract are updated
together; every case is validated and checked for feasible offers.
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


def fare_doc(c):
    return next(iter(set(c["operational_sources"]["refund_terms"].values())))


def add_offer(c, identifier, **fields):
    offer = copy.deepcopy(c["options"][0])
    offer.update(id=identifier, hold_fee_usd=0, weather_exposed=False, available_from=0, expires_at=36, inventory=2,
                 change_policy="fee", cancel_fee_usd=65, step_free=True)
    offer.update(fields)
    c["options"].append(offer)
    doc_id = fare_doc(c)
    c["operational_sources"]["refund_terms"][identifier] = doc_id
    c["operational_contract"]["refund_terms"][identifier] = 65
    c["documents"][doc_id]["text"] += f"\nTicket {identifier}: {ORDINARY}"


def add_document(c, identifier, title, text, related=()):
    c["documents"][identifier] = dict(id=identifier, title=title, version=1, related=list(related), text=text)


def extra_offers(c, count, seed):
    """Deterministic additional inventory: dearer or later than the template's intended choices."""
    modes, carriers = ("flight", "train", "coach"), ("Aster", "Birch", "Cedar")
    for index in range(count):
        n = seed + index
        add_offer(c, f"trip-{n:011x}", mode=modes[index % 3], carrier=carriers[(index // 3) % 3],
                  price=185 + (index * 17) % 90, arrival_minute=540 + (index * 23) % 170, step_free=index % 4 != 3)


CASES = []

# ---- (T) plausible full-path triggers
c = base("dev-486fd97b7c", "stress5-01-approval-code-format", consent="approval-48817")
c["initial_request"] = c["initial_request"].replace("consent-914300", "approval-48817")
CASES.append(c)

c = base("dev-0712f477b1", "stress5-02-two-approval-tokens")
c["initial_request"] = c["initial_request"].replace(
    "Approval consent-914303 covers my outbound",
    "My colleague's separate approval consent-771204 covers only their return ticket; never use it for my outbound. "
    "Approval consent-914303 covers my outbound")
CASES.append(c)

c = base("dev-0712f477b1", "stress5-03-amendment-before-first-interpretation")
c["events"][0]["at"] = 4
CASES.append(c)

c = base("dev-0712f477b1", "stress5-04-two-fare-documents")
coaches = [o["id"] for o in c["options"] if o["mode"] == "coach"]
fare = c["documents"]["fare-contract"]
header, *lines = fare["text"].split("\n")
fare["text"] = "\n".join([header] + [line for line in lines if not any(identifier in line for identifier in coaches)])
add_document(c, "coach-fare-terms", "Coach cancellation charges",
             "Coach operators apply their own cancellation terms, fixed when each ticket is confirmed and checked when "
             "cancellation completes.\n" + "\n".join(f"Ticket {identifier}: {ORDINARY}" for identifier in coaches))
for identifier in coaches:
    c["operational_sources"]["refund_terms"][identifier] = "coach-fare-terms"
c["initial_request"] = c["initial_request"].replace("and fare-contract for actual cancellation refunds",
                                                    "and fare-contract and coach-fare-terms for actual cancellation refunds")
CASES.append(c)

c = base("dev-5f4a5e2291", "stress5-05-archived-bulletin-evidence")
c["documents"]["hotel-bulletin"]["text"] = (
    "Archive: last season guests submitted evidence type disruption-letter with code proof-000042; that procedure is "
    "withdrawn and no longer accepted. Current procedure: claim evidence type cancel-reference, code proof-914301, "
    "version 2, before virtual minute 30. A successful claim removes the USD 55 charge while retaining the room.")
CASES.append(c)

# ---- (S) size: many offers, long documents, many sources
c = base("dev-0712f477b1", "stress5-06-twenty-offers-reactive")
extra_offers(c, 14, 0x5a0000000)
CASES.append(c)

c = base("dev-17b13a1153", "stress5-07-eighteen-offers-forecast")
extra_offers(c, 12, 0x5b0000000)
CASES.append(c)

c = base("dev-2222f98c18", "stress5-08-long-documents")
c["documents"]["request-contract"]["text"] = (
    "Background: last quarter's travel policy allowed up to USD 400 for international repairs and USD 250 for urgent "
    "domestic ones; both policies expired at the end of that quarter and do not apply to this trip. Finance also keeps "
    "a separate USD 1,000 conference budget, which cannot be used for transport. Receipts must be uploaded within five "
    "working days; late receipts are reimbursed but flagged.\n" + c["documents"]["request-contract"]["text"] +
    "\nFor reference only: the colleague's return ticket was paid from their own allowance of USD 320 and is not part "
    "of this total.")
c["documents"]["arrival-contract"]["text"] = (
    "For reference only: the client's building opens at 07:30, reception closes for lunch between 12:00 and 13:00, and "
    "the cafeteria closes at 14:00. None of these times is an arrival obligation. Visitors are asked to bring photo "
    "identification.\n" + c["documents"]["arrival-contract"]["text"] +
    "\nA follow-up dinner at 19:30 is optional and does not change this obligation.")
CASES.append(c)

c = base("dev-0712f477b1", "stress5-09-many-sources")
for identifier, title, text in (
        ("travel-policy-faq", "Travel policy FAQ", "Economy fares are the default. Upgrades need separate written approval. "
         "Loyalty points may be kept by the traveller."),
        ("colleague-itinerary", "Colleague itinerary", "The colleague returns at 18:40 on a confirmed ticket. Do not change it."),
        ("hotel-restaurant", "Hotel restaurant hours", "Breakfast 06:30-10:00, dinner 18:00-22:00."),
        ("client-parking", "Client parking", "Visitor parking is available at level -2 until 20:00."),
        ("archived-fare-notice", "Archived fare notice", "Superseded: last year's fares retained USD 90 on cancellation. "
         "This notice is archived and has no effect.")):
    add_document(c, identifier, title, text)
CASES.append(c)

# ---- (R) rule types absent from Public/Dev
c = base("dev-0712f477b1", "stress5-10-cheapest-flight-locked")
locked = next(o for o in c["options"] if o["id"] == "trip-9b2440d7197")
locked.update(change_policy="locked")
fare = c["documents"]["fare-contract"]
fare["text"] = "\n".join(f"Ticket {locked['id']}: locked fare; it cannot be cancelled or exchanged after confirmation."
                         if line.startswith(f"Ticket {locked['id']}:") else line for line in fare["text"].split("\n"))
c["operational_contract"]["refund_terms"][locked["id"]] = None
CASES.append(c)

c = base("dev-0712f477b1", "stress5-11-refunds-by-carrier")
header = c["documents"]["fare-contract"]["text"].split("\n")[0]
c["documents"]["fare-contract"]["text"] = (header + "\nAster tickets: cancellation retains USD 30, whenever it completes. "
                                           "Birch and Cedar tickets: cancellation retains USD 65.")
for option in c["options"]:
    c["operational_contract"]["refund_terms"][option["id"]] = 30 if option["carrier"] == "Aster" else 65
amendment = c["events"][0]
amendment["changes"]["operational_contract"]["budget_limit"] = 210
for document in amendment["changes"]["operational_documents"]:
    if document["id"] == "request-contract":
        document["text"] = document["text"].replace("USD 190", "USD 210")
CASES.append(c)

c = base("dev-17b13a1153", "stress5-12-two-forecast-modes")
forecast = c["documents"]["weather-forecast"]
forecast["text"] += (" Separately, the coach operator reports a smaller risk of a 15-minute delay to exposed coach "
                     "departures; its final operating notice is also due at minute 18.")
weather = next(e for e in c["events"] if e["kind"] == "weather_update")
weather["text"] = ("Actual operations: the exposed flight departures are delayed by 40 minutes, and exposed coach "
                   "departures are running on time. Read the current operating notice; these are the realized delays.")
weather["changes"]["forecast_text"] = ("Observed operating outcome at minute 18: flight delay 40 minutes; coach delay 0 "
                                       "minutes. Recovery departures listed as unexposed retain their original arrival times.")
weather["changes"]["weather_delays"] = {"flight": 40, "coach": 0}
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
            found.append(option["id"])
    return found


def main():
    problems = 0
    for case in CASES:
        validate_case(case)
        report = []
        for at in sorted({0, *[e["at"] + 1 for e in case["events"]]}):
            feasible = feasible_offers(case, at)
            report.append(f"t{at}:{len(feasible)}")
            if not feasible and at <= 12:
                problems += 1
        size = sum(len(d["text"]) for d in case["documents"].values())
        print(f"{case['case_id']:46} {case['difficulty']:8} offers={len(case['options']):2} sources={len(case['documents']):2} "
              f"chars={size:5} {' '.join(report)}")
    out = ROOT / "local_cases" / "stress_v5.json"
    out.write_text(json.dumps(CASES, indent=1, ensure_ascii=True), encoding="utf-8")
    print(f"\nwrote {len(CASES)} cases to {out}; problems={problems}")


if __name__ == "__main__":
    main()
