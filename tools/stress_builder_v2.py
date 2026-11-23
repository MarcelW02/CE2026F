"""Build stress_v2: harder contract logic on known v10 dynamics, for local diagnosis only.

Run from project/:  .venv/Scripts/python.exe -I ../tools/stress_builder_v2.py  (writes local_cases/stress_v2.json)

stress_v1 varied wording and structure. This bank keeps each template's offers, events and intended
solution path, but states the rules the way a harder case would: relative amounts, derived clock times,
tiered thresholds, exceptions, grouped ticket terms, split or combined amendments. Where the truth itself
changes, the intended path still satisfies it; every case is validated and checked for feasible offers.
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

V = lambda name: {"var": name}
CMP = lambda op, left, right: {"op": op, "left": left, "right": right}
IF = lambda when, then, otherwise: {"op": "if", "when": when, "then": then, "else": otherwise}
AND = lambda *args: {"op": "and", "args": list(args)}

FARE_HEADER_65 = ("Base fare fields describe ordinary cancellation: these fee fares normally retain USD 65. The following provider "
                  "terms override that amount. They are fixed when each ticket is confirmed; the conditions are checked when "
                  "cancellation actually completes. Cancellation uses the outbound consent. A hold is not a confirmed replacement, "
                  "and overlapping confirmed outbounds remain forbidden.\n")


def variant(source_id, new_id, docs=None, events=None, truth=None, event_truth=None):
    """Copy one case; replace document texts, event texts/doc texts and (optionally) truth expressions."""
    c = copy.deepcopy(ALL[source_id])
    c["case_id"] = new_id
    for doc_id, text in (docs or {}).items():
        c["documents"][doc_id]["text"] = text
    for index, new in (events or {}).items():
        event = c["events"][index]
        event["text"] = new.get("text", event["text"])
        for document in event["changes"].get("operational_documents", []):
            if document["id"] in new.get("docs", {}):
                document["text"] = new["docs"][document["id"]]
        for field in ("document_text", "forecast_text"):
            if field in new:
                event["changes"][field] = new[field]
    c["operational_contract"].update(truth or {})
    for index, changes in (event_truth or {}).items():
        c["events"][index]["changes"]["operational_contract"] = changes
    return c


CASES = []

# ------------------------------------------------------------------ Forecast (template dev-17b13a1153 unless stated)
# Intended path: hold a sheltered recovery before sales close at 14, keep or replace the booking after the
# minute-18 report of an actual 40-minute flight delay; the exposed tickets then refund fully.
CASES.append(variant("dev-17b13a1153", "stress2-01-forecast-additive-supplement", docs={"request-contract":
    "My base allowance for the whole repair is USD 145. Once an operating notice reports that flight services are actually "
    "running at least half an hour late, a USD 45 disruption supplement is added to it. A forecast or warning never triggers "
    "the supplement. Retained cancellation charges and any hotel charge count against the allowance with or without the supplement."}))

CASES.append(variant("dev-17b13a1153", "stress2-02-forecast-sheltered-only-supplement", docs={"request-contract":
    "The spending ceiling is USD 145. After an actual flight delay of at least 30 minutes has been reported, a ceiling of USD 190 "
    "applies, but only to a departure that is not exposed to the weather; any weather-exposed ticket stays under the USD 145 "
    "ceiling. Forecasts do not count as a reported delay. Both ceilings include retained cancellation charges and any hotel charge."},
    truth={"budget_limit": IF(AND(CMP("ge", V("state.weather.flight"), 30), CMP("eq", V("candidate.weather_exposed"), False)), 190, 145)}))

CASES.append(variant("dev-17b13a1153", "stress2-03-forecast-tiered-supplement", docs={"request-contract":
    "Spending is limited to USD 145 in total. If an actual flight delay of 30 minutes or more is observed, the limit becomes USD 190; "
    "if the observed delay reaches 90 minutes, it becomes USD 240. Forecast figures never change the limit. All limits include "
    "retained cancellation charges and any hotel charge."},
    truth={"budget_limit": IF(CMP("ge", V("state.weather.flight"), 90), 240, IF(CMP("ge", V("state.weather.flight"), 30), 190, 145))}))

CASES.append(variant("dev-17b13a1153", "stress2-04-forecast-derived-deadline", docs={"arrival-contract":
    "The client meeting starts at 11:45, and I must be at the client half an hour before it starts. The transfer in "
    "transport-guide counts toward that."}))

CASES.append(variant("dev-17b13a1153", "stress2-05-forecast-raised-estimate", events={0: dict(
    text="Forecast version 2: the flight delay estimate has been raised. Spending approvals are unchanged.",
    document_text="Revised outlook: the possible flight delay is now estimated at 55 minutes and remains uncertain. The actual "
                  "operating notice still follows at minute 18; recovery sales close at minute 14, and an earlier live hold "
                  "stays valid until its stated expiry.")}))

c = variant("dev-700f85cf1a", "stress2-06-forecast-grouped-ticket-terms", docs={"fare-contract": FARE_HEADER_65 +
    "Tickets trip-c5af493871d and trip-a9b7e2ed55c: if the coach operator has actually reported a delay of 30 minutes or longer, a "
    "cancellation finished no later than virtual minute 24 is refunded completely; otherwise, and for any later cancellation, "
    "USD 65 is kept.\nAll other tickets: USD 65 is kept on cancellation, without exceptions."})
CASES.append(c)

CASES.append(variant("dev-ae66140cb6", "stress2-07-forecast-held-refund-reworded", docs={
    "request-contract": "Total spending may reach USD 155. Should the train operator actually report a delay of 35 minutes or more, "
                        "the cap rises to USD 200; a forecast does not count. Retained cancellation charges and any hotel charge are "
                        "part of the total under either cap.",
    "fare-contract": FARE_HEADER_65 +
        "Ticket trip-590005b4b7b: a complete refund applies only if, when the cancellation finishes, an actual train delay of at "
        "least 35 minutes has been reported and you are holding a live replacement whose fare is at most USD 190 and which "
        "reaches the client by 09:50. In any other case USD 65 is kept.\n"
        "Ticket trip-80bb93ba9da: same rule as trip-590005b4b7b.\n"
        "Ticket trip-76e6ac4c0e4: ordinary cancellation retains USD 65; there is no additional exception.\n"
        "Ticket trip-58e324458fe: ordinary cancellation retains USD 65; there is no additional exception.\n"
        "Ticket trip-672e67d1966: ordinary cancellation retains USD 65; there is no additional exception.\n"
        "Ticket trip-96dbb322c3b: ordinary cancellation retains USD 65; there is no additional exception."}))

CASES.append(variant("travel-9f7c83790326d2761f54", "stress2-08-forecast-service-window-reworded", docs={
    "request-contract": "Ordinary ceiling: USD 170. Emergency ceiling: USD 220, which applies only to a payment completing at or "
                        "before virtual minute 26, and only once actual operating information shows flight delays of thirty minutes "
                        "or more. Payments after minute 26 fall back under USD 170. A forecast does not unlock the emergency ceiling. "
                        "Both ceilings include retained charges and any hotel fee.",
    "arrival-contract": "Be at the client no later than five past eleven (11:05), transfer included. The emergency spending window "
                        "does not move this appointment."}))

# ------------------------------------------------------------------ Reactive
CASES.append(variant("dev-0712f477b1", "stress2-09-reactive-relative-amendments", events={0: dict(
    text="Two changes from me, both effective now. Please re-read the spending approval and the arrival obligation; nothing else changes.",
    docs={"request-contract": "The spending ceiling goes up by USD 45 compared with the previous approval. It is still one total, "
                              "including any retained cancellation charge and any hotel fee.",
          "arrival-contract": "The client has moved my required arrival forward by 85 minutes compared with the previous deadline; "
                              "the transfer still counts. Keep step-free access and the other conditions."})}))

CASES.append(variant("dev-0712f477b1", "stress2-10-reactive-spelled-amendments", events={0: dict(
    docs={"request-contract": "New total ceiling: one hundred and ninety US dollars, retained cancellation charges and any hotel fee "
                              "included. It replaces the earlier ceiling rather than adding to it.",
          "arrival-contract": "Please be at the client by ten minutes to ten in the morning, transfer included. This replaces the "
                              "earlier deadline; keep step-free access and all other current conditions."})}))

CASES.append(variant("dev-2222f98c18", "stress2-11-reactive-train-only-later-deadline", events={0: dict(
    docs={"arrival-contract": "New arrival obligation: reach the client by 09:50, transfer included. Because trains stop next to "
                              "the client site, a train may arrive as late as 10:00 instead. This replaces the earlier deadline."})},
    event_truth={0: {"budget_limit": 200, "arrival_deadline": IF(CMP("eq", V("candidate.mode"), "train"), 600, 590)}}))

c = variant("dev-d1e8acd8cc", "stress2-12-reactive-split-amendments")
first = c["events"][0]
budget_doc = next(d for d in first["changes"]["operational_documents"] if d["id"] == "request-contract")
arrival_doc = next(d for d in first["changes"]["operational_documents"] if d["id"] == "arrival-contract")
budget_doc["text"] = ("The total additional-spending ceiling is now USD 205, replacing the previous ceiling. Include any retained "
                      "cancellation charge and any hotel fee.")
arrival_doc["text"] = "Reach the client by 09:50 including the current transfer. The earlier deadline is replaced."
c["events"] = [
    dict(at=13, kind="user_update", text="Finance has raised my spending approval; please read it again. The arrival obligation is "
                                         "unchanged for now.",
         changes=dict(operational_contract={"budget_limit": 205}, operational_documents=[budget_doc])),
    dict(at=17, kind="user_update", text="The client moved the appointment earlier; read the updated arrival obligation. Spending "
                                         "stays as last approved.",
         changes=dict(operational_contract={"arrival_deadline": 590}, operational_documents=[arrival_doc])),
]
CASES.append(c)

c = variant("travel-7b1558c214cd1bd41e92", "stress2-13-reactive-combined-notice")
supplement, ban = c["events"]
supplement["text"] = ("Spending approval revised for coach recovery only; see the updated approval. Separately, Aster is now "
                      "off-limits for my outbound. The arrival obligation and fare conditions are unchanged.")
supplement["changes"]["avoid_carriers"] = ban["changes"]["avoid_carriers"]
supplement["changes"]["operational_documents"][0]["text"] = (
    "Exception to the USD 180 ceiling: a coach booking may go up to USD 210 in total if it is step-free, reaches the client by "
    "10:45, and no earlier cancellation has retained more than USD 25. Anything that misses even one of these conditions stays "
    "under USD 180. The USD 210 is the new total, not an addition.")
c["events"] = [supplement]
CASES.append(c)

# ------------------------------------------------------------------ Basic
CASES.append(variant("dev-486fd97b7c", "stress2-14-basic-relative-mode-ceiling", docs={"request-contract":
    "A flight may use a total of up to USD 145. Every other mode gets USD 40 less than that. These totals include retained "
    "cancellation charges and the hotel charge."}))

CASES.append(variant("dev-5f4a5e2291", "stress2-15-basic-derived-registration", docs={"arrival-contract":
    "The 10:00 briefing requires registration, and the registration desk at the client closes twenty minutes before the briefing "
    "starts. I must be registered, so I need to reach the client by the time the desk closes, transfer included."}))

CASES.append(variant("dev-dfc8cdde33", "stress2-16-basic-within-reference", docs={"request-contract":
    "Coach fares within USD 20 of the cheapest ticket that currently reaches the client by 10:55 unlock a USD 170 total; in every "
    "other case the total is USD 125. Only tickets reaching the client by 10:55 can set that reference, and if none does, the "
    "USD 125 total applies. Retained fees and the hotel charge are part of the total."}))

CASES.append(variant("travel-30a97ab15337e7084969", "stress2-17-basic-exception-to-concession", docs={"arrival-contract":
    "Coach travel earns a 30-minute later deadline (11:30 instead of 11:00), except for coach fares over USD 130, which keep the "
    "11:00 deadline. Client arrival times include the transfer."}))

CASES.append(variant("travel-7be0e09bbe903f5ab848", "stress2-18-basic-quote-reordered", docs={"request-contract":
    "I approve the cheapest qualifying quote plus USD 35, capped at USD 190 in total; USD 190 also applies if nothing qualifies. "
    "A qualifying quote is step-free, currently available, not operated by Cedar, and gets me to the client by 11:00. The total "
    "covers the ticket, retained charges and any hotel amount still due; the USD 35 is not a second allowance. Currently available "
    "quotes include unheld inventory still on sale and the particular option now being considered if your own live hold preserves "
    "it after sales close. Other held options are not automatically included; a condition that calls for a live hold checks held "
    "options separately."}))


# ------------------------------------------------------------------ checks
def feasible_offers(case, at):
    world = world_for_case(copy.deepcopy(case), concurrency=3)
    world._advance(at)
    found = []
    for option in world._options.values():
        on_sale = option["inventory"] > 0 and option.get("available_from", 0) <= world.now < option["expires_at"]
        if not on_sale:
            continue
        rules = world._rules
        if (option["price"] <= world._limit(option) and world._offer_facts(option)["meeting_arrival"] <= world._deadline(option)
                and (not rules["requires_step_free"] or option["step_free"]) and option["carrier"] not in rules["avoid_carriers"]):
            found.append(option["id"])
    return sorted(found)


def main():
    problems = 0
    for case in CASES:
        validate_case(case)
        source = next(s for s in ALL.values() if s["seed"] == case["seed"] and s["family"] == case["family"])
        report = []
        for at in sorted({0, *[e["at"] + 1 for e in case["events"]]}):
            mine, theirs = feasible_offers(case, at), feasible_offers(source, at)
            report.append(f"t{at}:{len(mine)}" + ("" if mine == theirs else f"(orig {len(theirs)})"))
            if not mine and at <= 12:
                problems += 1
                report.append("NO FEASIBLE OFFER")
        print(f"{case['case_id']:46} {case['difficulty']:8} {' '.join(report)}")
    out = ROOT / "local_cases" / "stress_v2.json"
    out.write_text(json.dumps(CASES, indent=1, ensure_ascii=True), encoding="utf-8")
    print(f"\nwrote {len(CASES)} cases to {out}; problems={problems}")


if __name__ == "__main__":
    main()
