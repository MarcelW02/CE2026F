"""Build stress_v3: planner situations (timing, inventory, interruptions, mid-trip changes), for local diagnosis only.

Run from project/:  .venv/Scripts/python.exe -I ../tools/stress_builder_v3.py  (writes local_cases/stress_v3.json)

The course slides list the Reactive situations (meeting, budget, preference, waiver, inventory, interrupted reply,
transfer and traveller-scope changes) and show a new request and a revised forecast at virtual minute 8, before
the first booking is due at minute 12. These cases keep the published wording and contract truth of their
templates and add those situations at realistic times, so failures point at the planner rather than at
interpretation. Every case is validated; feasibility is checked with the world's own rules.
"""
import copy
import json
import sys
from pathlib import Path

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT))
from framework.world_factory import validate_case, world_for_case  # noqa: E402

PUB = {c["case_id"]: c for c in json.loads((ROOT / "data/public.json").read_text(encoding="utf-8"))}
DEV = {c["case_id"]: c for c in json.loads((ROOT / "data/dev.json").read_text(encoding="utf-8"))}
ALL = {**PUB, **DEV}


def base(source_id, new_id, **fields):
    c = copy.deepcopy(ALL[source_id])
    c["case_id"] = new_id
    c.update(fields)
    return c


def add(c, at, kind, text, **changes):
    c["events"].append(dict(at=at, kind=kind, text=text, changes=changes))
    c["events"].sort(key=lambda event: event["at"])
    return c


def renumber_forecast_versions(c):
    """Forecast versions must rise with each forecast or weather event."""
    version = c["documents"]["weather-forecast"]["version"]
    for event in c["events"]:
        if event["kind"] in ("forecast_update", "weather_update") and "forecast_version" in event["changes"]:
            version += 1
            event["changes"]["forecast_version"] = version
    return c


def cheapest_preferred(c):
    """The option a cost-minimising planner books first: cheapest feasible offer in the preferred mode."""
    world = world_for_case(copy.deepcopy(c), concurrency=3)
    best = None
    for option in world._options.values():
        if (option["mode"] == world._rules["preferred"] and option.get("available_from", 0) == 0
                and option["price"] <= world._limit(option)
                and world._offer_facts(option)["meeting_arrival"] <= world._deadline(option)
                and (not world._rules["requires_step_free"] or option["step_free"])
                and option["carrier"] not in world._rules["avoid_carriers"]):
            if best is None or option["price"] < best["price"]:
                best = option
    return best["id"]


def revised_outlook(mode, delay):
    return dict(
        text=f"Forecast version 2: the {mode} risk has risen. Read the revised outlook before recovery sales close.",
        document_text=(f"Revised outlook: a 75 percent chance that exposed {mode} departures are delayed by about {delay} "
                       "minutes. This is still a forecast, not an actual delay. The final operating notice arrives at minute 18; "
                       "recovery sales close at minute 14, and a live hold stays usable until its own expiry. Each recovery hold "
                       "still charges USD 20 now, credited once if confirmed."))


CASES = []

# ---- Early events before the first booking is due at minute 12 (slides: new request / revised forecast at minute 8)
c = base("dev-0712f477b1", "stress3-01-early-amendment-at-8")
c["events"][0]["at"] = 8
CASES.append(c)

c = base("dev-2222f98c18", "stress3-02-early-amendment-at-6")
c["events"][0]["at"] = 6
CASES.append(c)

c = base("dev-0712f477b1", "stress3-03-early-carrier-ban-at-8")  # Birch flights stay feasible without Aster
add(c, 8, "user_update", "Before you book: Aster is no longer permitted for my outbound. All other conditions continue.",
    avoid_carriers=["Aster"])
CASES.append(c)

for source, new_id, mode, delay in (("dev-17b13a1153", "stress3-04-revised-forecast-at-8-flight", "flight", 60),
                                    ("dev-700f85cf1a", "stress3-05-revised-forecast-at-8-coach", "coach", 60),
                                    ("travel-9f7c83790326d2761f54", "stress3-06-revised-forecast-at-8-public", "flight", 55)):
    c = base(source, new_id)
    outlook = revised_outlook(mode, delay)
    add(c, 8, "forecast_update", outlook["text"], document_text=outlook["document_text"], forecast_version=0)
    CASES.append(renumber_forecast_versions(c))

# ---- Interrupted confirmation replies (slides: "a booking may commit before its reply arrives")
CASES.append(base("dev-486fd97b7c", "stress3-07-interrupted-reply-basic", interrupt_confirmation=True))
CASES.append(base("dev-2222f98c18", "stress3-08-interrupted-reply-reactive", interrupt_confirmation=True))
CASES.append(base("dev-17b13a1153", "stress3-09-interrupted-reply-forecast", interrupt_confirmation=True))

# ---- Inventory: a warned sellout of the option a cheapest-first planner would book (generator pattern: warn 8, sell 12)
for source, new_id in (("dev-2222f98c18", "stress3-10-sellout-of-first-choice-reactive"),
                       ("dev-486fd97b7c", "stress3-11-sellout-of-first-choice-basic")):
    c = base(source, new_id)
    target = cheapest_preferred(c)
    add(c, 8, "stock_update", f"A competing buyer will take unheld inventory for {target} at virtual minute 12. A valid hold "
                              "protects seats.")
    add(c, 12, "sellout", f"Option {target} is now sold out to other buyers. Existing holds and bookings are unaffected.",
        option_id=target)
    CASES.append(c)

c = base("dev-17b13a1153", "stress3-12-sellout-of-recovery")
add(c, 8, "stock_update", "A competing buyer will take unheld inventory for trip-d06ecadd99e at virtual minute 12. A valid hold "
                          "protects seats.")
add(c, 12, "sellout", "Option trip-d06ecadd99e is now sold out to other buyers. Existing holds and bookings are unaffected.",
    option_id="trip-d06ecadd99e")
CASES.append(c)

# ---- Mid-trip changes that invalidate the current booking
c = base("dev-d1e8acd8cc", "stress3-13-midtrip-carrier-ban")
c["events"] = []
add(c, 16, "user_update", "Please stop using Aster for my outbound from now on; any other listed carrier is fine. Everything "
                          "else stays as it is.", avoid_carriers=["Aster"])
CASES.append(c)

c = base("dev-0712f477b1", "stress3-14-transfer-change-after-amendment")
add(c, 18, "transport_update", "A road closure lengthens the onward transfer for flight arrivals. Read the current "
                               "transport-guide before keeping or choosing a replacement.",
    transfer=dict(flight=30, train=20, coach=20),
    document_text="Add 30 minutes to terminal arrival for a flight and 20 minutes for a train or coach. The result is arrival "
                  "at the client, not terminal arrival.")
CASES.append(c)

c = base("dev-5f4a5e2291", "stress3-15-waiver-revision-at-4")
add(c, 4, "document_update", "The hotel replaced hotel-bulletin. Claims still pending must use the new procedure; claims "
                             "already accepted stand.",
    waiver="disruption-letter", waiver_version=3,
    document_text="Claim evidence type disruption-letter, code proof-914301, version 3, before virtual minute 30. A successful "
                  "claim removes the USD 55 charge while retaining the room.")
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
    return sorted(found)


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
                report.append("NO FEASIBLE OFFER")
        events = ", ".join(f"{e['kind']}@{e['at']}" for e in case["events"])
        print(f"{case['case_id']:46} {case['difficulty']:8} {' '.join(report):24} [{events}]"
              + ("  interrupt" if case["interrupt_confirmation"] else ""))
    out = ROOT / "local_cases" / "stress_v3.json"
    out.write_text(json.dumps(CASES, indent=1, ensure_ascii=True), encoding="utf-8")
    print(f"\nwrote {len(CASES)} cases to {out}; problems={problems}")


if __name__ == "__main__":
    main()
