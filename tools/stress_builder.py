"""Build stress_v1: reworded and structurally varied v10 cases for local diagnosis only.

Run from project/:  .venv/Scripts/python.exe -I <this file>  (writes local_cases/stress_v1.json)
Every case is validated with the framework's own validator, and its solvability is checked
with the world's own truth rules (feasible on-sale offers at the start and after each event).
"""
import copy
import json
import re
import sys
from pathlib import Path

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT))
from framework.world_factory import validate_case, world_for_case  # noqa: E402

PUB = {c["case_id"]: c for c in json.loads((ROOT / "data/public.json").read_text(encoding="utf-8"))}
DEV = {c["case_id"]: c for c in json.loads((ROOT / "data/dev.json").read_text(encoding="utf-8"))}
ALL = {**PUB, **DEV}


# ---------------------------------------------------------------- shared rewording
def request_text(c, budget_id, arrival_id, fare_id):
    original = c["initial_request"]
    dest = re.search(r"outbound to ([\w -]+?)\.", original)[1]
    mode = re.search(r"Prefer (flight|train|coach)", original)[1]
    excluded = re.search(r"Do not use ([\w -]+)\.", original)
    consent = re.search(r"\bconsent-[\w-]+\b", original)[0]
    first = re.search(r"required by virtual minute (\d+)", original)[1]
    parts = [
        f"My outbound to {dest} was cancelled, so please rebook it.",
        f"A {mode} is my preferred option whenever a suitable {mode} is affordable, and I need step-free access.",
        f"Please avoid {excluded[1]}; any other listed carrier is fine." if excluded else "Every listed carrier is acceptable.",
        "Leave the existing hotel booking and my colleague's return as they are, but do claim the hotel charge waiver.",
        f"I authorize {consent} for my outbound and any permitted cancellation of it, within the spending conditions in {budget_id}.",
        f"The binding arrival obligation is in {arrival_id}; transfers are in transport-guide, and actual cancellation refunds in {fare_id}.",
        f"I need a first confirmed replacement no later than virtual minute {first}.",
    ]
    handoff = re.search(r"handing it over at or after minute (\d+)", original)
    if handoff:
        parts.append(f"Check the booking before you hand it over, at minute {handoff[1]} or later.")
    else:
        watch, finish = re.search(r"through minute (\d+) and finish by minute (\d+)", original).groups()
        parts.append(f"Further partial changes may follow. Keep watching current notices until minute {watch} and finish by minute {finish}.")
    if "Read weather-forecast" in original:
        parts.append("Look at weather-forecast before the recovery sales close. The announced risk is uncertain, "
                     "and a later operating notice will state what actually happened.")
    parts.append("All clock times and arrival minutes are local time after midnight, while virtual minutes count elapsed tool time. "
                 "Spending authorization is checked when a charged action completes, and a later lower allowance "
                 "does not cancel a payment that was authorized earlier.")
    return " ".join(parts)


def profile_text(c):
    mode, excluded = c["preferred"], c["avoid_carriers"]
    text = (f"A suitable {mode} is preferred when it is affordable. Step-free access is required. "
            "My colleague's separate return and our existing hotel are not part of this request.")
    return text + (f" {excluded[0]} must not be used." if excluded else "")


def transfer_text(minutes):
    return (f"Client transfer: add {minutes} minutes to the terminal arrival time for any mode (flight, train or coach). "
            "That sum is the arrival time at the client, not at the terminal.")


def bulletin_text(c):
    return (f"To waive the USD 55 hotel charge, submit evidence type {c['waiver_type']} with code {c['waiver_code']} "
            "and this bulletin's version 2 before virtual minute 30. The room is kept in every case.")


HOTEL_TERMS = "Keep the room. The linked hotel-bulletin describes the current evidence that removes the USD 55 charge."

FARE_HEADER = re.compile(r"Base fare fields describe ordinary cancellation: these fee fares normally retain USD (\d+)\. .*?forbidden\.\n", re.S)

CLAUSES = [
    (r"[Oo]rdinary cancellation retains USD (\d+); there is no additional exception\.",
     r"the standard USD \1 is kept on cancellation, with no exception."),
    (r"Cancellation completed by virtual minute (\d+), inclusive, receives a full refund\. Later cancellation retains USD (\d+)\.",
     r"a cancellation that completes at or before virtual minute \1 is refunded in full; any later cancellation keeps USD \2."),
    (r"Cancellation completed by minute (\d+) retains USD (\d+), otherwise USD (\d+)\.",
     r"if the cancellation completes by minute \1, USD \2 is kept; after that, USD \3 is kept."),
    (r"At cancellation, hold an unexpired replacement reaching the client by (\S+) with fare at most USD (\d+); this qualifies "
     r"for a full refund\. Without such a live hold, cancellation retains USD (\d+)\. Merely finding an offer does not qualify\.",
     r"the fare is refunded in full only if, when the cancellation completes, you hold a live, unexpired replacement that gets me "
     r"to the client by \1 and costs no more than USD \2. Otherwise USD \3 is kept. An offer that is merely visible in search does not count."),
    (r"A full refund is available when an actual (\w+) delay of at least (\d+) minutes has been observed\. A forecast alone does "
     r"not qualify\. Otherwise cancellation retains USD (\d+)\.",
     r"refunded in full once an actual \1 delay of at least \2 minutes has been observed; a forecast is not enough. Without that, USD \3 is kept."),
    (r"A full refund requires an observed (\w+) delay of at least (\d+) minutes and a live held replacement costing at most USD (\d+) "
     r"that reaches the client by (\S+)\. Both conditions must hold when cancellation completes\. Otherwise USD (\d+) is retained\.",
     r"a full refund only when, at the moment cancellation completes, an observed \1 delay of at least \2 minutes exists and you also "
     r"hold a live replacement costing at most USD \3 that reaches the client by \4. In every other situation USD \5 is kept."),
    (r"When an actual (\w+) delay of at least (\d+) minutes is observed, cancellation completed by minute (\d+) receives a full refund\. "
     r"After that cutoff, or without the observed delay, USD (\d+) is retained\.",
     r"if an actual \1 delay of at least \2 minutes has been observed, a cancellation completing by minute \3 is refunded in full; "
     r"later cancellations, or any without that observed delay, keep USD \4."),
    (r"Cancellation retains USD (\d+) from the ticket price\. The balance is refunded\.",
     r"Whichever ticket is cancelled, USD \1 of its price is kept and the rest is refunded."),
    (r"If a ticket is cancelled, the provider retains USD (\d+) and refunds the rest\.",
     r"When a ticket is cancelled, the provider keeps USD \1 and refunds the remainder."),
    (r"Ordinary cancellation retains USD (\d+)\. An exposed flight ticket receives a full refund when cancellation completes by "
     r"virtual minute (\d+) and the actual flight delay is at least thirty minutes\. Both requirements must be met\. Sheltered "
     r"flights and other modes keep the ordinary charge, even during the disruption\.",
     r"Ordinary cancellation keeps USD \1. An exposed flight ticket is refunded in full if the cancellation completes by virtual "
     r"minute \2 and the actual flight delay is at least thirty minutes; both requirements must hold. Sheltered flights and all "
     r"other modes keep the ordinary charge, even during the disruption."),
]


def reword_fare(text, line_style):
    header = FARE_HEADER.match(text)
    base = header[1]
    body = text[header.end():]
    new_header = (f"Ordinary cancellation is described by the base fare fields: these fee fares normally keep USD {base}. "
                  "The provider terms below replace that amount. Each ticket's terms are fixed when it is confirmed, and their "
                  "conditions are evaluated when the cancellation actually completes. Cancelling uses the outbound consent. "
                  "A hold does not count as a confirmed replacement, and two overlapping confirmed outbounds are never allowed.\n")
    lines = []
    for line in body.split("\n"):
        ticket = re.fullmatch(r"Ticket ([\w-]+): (.+)", line)
        clause = ticket[2] if ticket else line
        for pattern, replacement in CLAUSES:
            if re.fullmatch(pattern, clause):
                clause = re.sub(pattern, replacement, clause)
                break
        else:
            raise ValueError("No rewording for clause: " + clause)
        if not ticket:
            lines.append(clause[0].upper() + clause[1:])
        elif line_style == "dash":
            lines.append(f"- {ticket[1]}: {clause}")
        else:
            lines.append(f"For ticket {ticket[1]}, {clause}")
    return new_header + "\n".join(lines)


def rename_docs(c, renames):
    """Rename operational documents everywhere: catalog, sources, related links, request and events."""
    for old, new in renames.items():
        document = c["documents"].pop(old)
        document["id"] = new
        c["documents"][new] = document
    for document in c["documents"].values():
        document["related"] = [renames.get(r, r) for r in document["related"]]
    sources = c["operational_sources"]
    for key in ("budget_limit", "arrival_deadline"):
        sources[key] = renames.get(sources[key], sources[key])
    sources["refund_terms"] = {k: renames.get(v, v) for k, v in sources["refund_terms"].items()}
    for event in c["events"]:
        for document in event["changes"].get("operational_documents", []):
            document["id"] = renames.get(document["id"], document["id"])


def base_variant(source_id, new_id, renames, texts, line_style="for", events=None, forecast=None):
    """Reword every text of one case; renames maps request/arrival/fare document IDs."""
    c = copy.deepcopy(ALL[source_id])
    c["case_id"] = new_id
    budget_id = renames.get("request-contract", "request-contract")
    arrival_id = renames.get("arrival-contract", "arrival-contract")
    fare_id = renames.get("fare-contract", "fare-contract")
    c["initial_request"] = request_text(c, budget_id, arrival_id, fare_id)
    docs = c["documents"]
    docs["traveler-profile"]["text"] = profile_text(c)
    docs["transport-guide"]["text"] = transfer_text(c["transfer"]["flight"])
    docs["hotel-bulletin"]["text"] = bulletin_text(c)
    docs["hotel-terms"]["text"] = HOTEL_TERMS
    docs["fare-contract"]["text"] = reword_fare(docs["fare-contract"]["text"], line_style)
    docs["request-contract"]["text"] = texts["budget"]
    docs["arrival-contract"]["text"] = texts["arrival"]
    if forecast is not None:
        docs["weather-forecast"]["text"] = forecast
    for event, new in zip(c["events"], events or []):
        event["text"] = new["text"]
        for document in event["changes"].get("operational_documents", []):
            document["text"] = new["docs"][document["id"]]
        for field in ("document_text", "forecast_text"):
            if field in event["changes"]:
                event["changes"][field] = new[field]
    rename_docs(c, renames)
    return c


R1 = {"request-contract": "finance-approval", "arrival-contract": "client-deadline", "fare-contract": "provider-terms"}
R2 = {"request-contract": "budget-memo", "arrival-contract": "site-access", "fare-contract": "ticket-rules"}
R3 = {"request-contract": "spending-rule", "arrival-contract": "meeting-terms", "fare-contract": "fare-rider"}

UPDATE_DOCS = lambda budget, budget_text, arrival_text: {"request-contract": budget_text, "arrival-contract": arrival_text}

CASES = []

# ---- Basic
CASES.append(base_variant("dev-486fd97b7c", "stress-01-mode-scoped-reworded", R1, dict(
    budget="Spending approval for my outbound: if the ticket I end up buying is a flight, total additional spending may reach "
           "USD 145. If it is any other mode, the total ceiling is USD 105. Both totals cover retained cancellation charges and "
           "the hotel charge. An older approval of USD 400 for a different trip does not apply here.",
    arrival="I must be at the client by 10:55, and the transfer from the terminal counts toward that time. Lunch at 11:40 is optional.")))
CASES.append(base_variant("dev-5f4a5e2291", "stress-02-registration-reworded", R2, dict(
    budget="The whole repair may cost at most USD 200 in total, counting retained cancellation charges and any hotel fee.",
    arrival="The meeting itself starts at 11:15. However, entry requires registering at the client site, and registration closes "
            "at 09:40, so I have to reach the client by 09:40, transfer included. Coffee after the meeting is optional and changes nothing."),
    line_style="dash"))
CASES.append(base_variant("dev-dfc8cdde33", "stress-03-fare-reference-reworded", R3, dict(
    budget="Reference fare: the cheapest ticket currently on offer that reaches the client by 10:55. If I take a coach whose fare is "
           "no more than USD 20 above that reference fare, total spending up to USD 170 is approved. In every other case the total "
           "allowance is USD 125. Tickets that arrive too late are left out of the comparison, so a cheap but late fare is never the "
           "reference. When no ticket currently on offer reaches the client by 10:55, the higher allowance is not available and "
           "USD 125 applies. Retained fees and the hotel charge count toward total spending.",
    arrival="Arrival at the client is due by 10:55, after adding the current terminal transfer.")))
CASES.append(base_variant("travel-7be0e09bbe903f5ab848", "stress-10-quote-allowance-reworded", R1, dict(
    budget="Spending reference: take the cheapest quote that is currently available, step-free, not operated by Cedar, and gets me "
           "to the client by 11:00. I approve that fare plus USD 35 for the entire repair, but never more than USD 190 in total. If no "
           "quote meets those conditions, the ceiling is USD 190. The total covers the ticket, retained charges and any hotel amount "
           "still due, and the USD 35 is not a second allowance. Currently available quotes are unheld inventory that is still on "
           "sale, plus the option now being considered when your own live hold keeps it available after sales close. Other held "
           "options are not automatically part of that quote set; any condition that requires a live hold checks held options separately.",
    arrival="I need to be with the client by 11:00, counting the current transfer from the terminal.")))
CASES.append(base_variant("travel-30a97ab15337e7084969", "stress-11-coach-concession-reworded", R2, dict(
    budget="For this repair the approved total is USD 180, which already includes retained charges and any hotel fee. The coach "
           "arrival concession does not raise this amount.",
    arrival="My normal arrival deadline at the client is 11:00. If the service I travel on is a coach, 11:30 is also acceptable, "
            "unless that coach ticket costs more than USD 130, in which case the 11:00 deadline still applies. Both are arrival "
            "times at the client, so add the transfer.")))

# ---- Reactive
def reactive_update(budget_value, notice):
    return [dict(text=notice, docs={
        R_ID: (f"From now on the total extra-spending cap is USD {budget_value}. It replaces the old cap; it is not added on top of "
               "it. Retained cancellation charges and any hotel fee count toward it. Refund conditions and the current arrival "
               "obligation stay as they are unless amended separately."),
        A_ID: ("New deadline: I must reach the client by 09:50, including the current transfer. This replaces the earlier deadline. "
               "Step-free access and all other current outbound conditions still apply."),
    })]


R_ID, A_ID = "request-contract", "arrival-contract"
CASES.append(base_variant("dev-0712f477b1", "stress-04-refund-cutoff-reworded", R1, dict(
    budget="The total extra spending for this trip is capped at USD 145. That cap covers the ticket itself, everything retained on "
           "tickets cancelled earlier, and any hotel charge still to be paid.",
    arrival="I have to be at the client by 11:15; the transfer listed in transport-guide counts toward this."),
    events=reactive_update(190, "I have revised the spending approval and the client deadline; please read both again. Nothing "
                                "else changes: the provider refund conditions and my other requirements still hold.")))
CASES.append(base_variant("dev-2222f98c18", "stress-05-held-replacement-reworded", R2, dict(
    budget="Additional spending must stay at or below USD 155 in total, counting the current ticket, amounts retained on earlier "
           "cancelled tickets, and any hotel charge still payable.",
    arrival="Reach the client by 11:15. The transfer in transport-guide counts toward this deadline."),
    line_style="dash",
    events=reactive_update(200, "Two of your sources were updated: the spending approval and the arrival obligation. Please re-read "
                                "them; refund conditions and every other requirement are unchanged.")))
CASES.append(base_variant("dev-d1e8acd8cc", "stress-06-retained-fee-reworded", R3, dict(
    budget="Total additional spending is capped at USD 165. The ticket, every amount retained on earlier cancelled tickets, and any "
           "hotel charge still payable all count toward the cap.",
    arrival="The client deadline is 11:15. Count the transfer from transport-guide."),
    events=reactive_update(205, "Please read the updated spending approval and arrival obligation. Only what those updates name is "
                                "changing; the provider's refund conditions and all my other requirements continue.")))
CASES.append(base_variant("travel-7b1558c214cd1bd41e92", "stress-12-narrow-supplement-reworded", R1, dict(
    budget="Total additional spending of up to USD 180 is approved, counting retained ticket charges and any hotel fee.",
    arrival="I need to reach the client by 11:15, current transfer included."),
    events=[dict(text="I have approved a limited recovery supplement for coach travel. Please read the revised spending approval; the "
                      "arrival obligation and the fare conditions are unchanged.",
                 docs={R_ID: "The total may now go up to USD 210, but only for a step-free coach that gets me to the client by 10:45, "
                             "and only as long as earlier ticket cancellations have retained no more than USD 25. For a booking that "
                             "meets all of those conditions this replaces the USD 180 ceiling; every other choice is still limited to "
                             "USD 180. The appointment and the provider's refund terms are as before, and the supplement does not add "
                             "USD 210 on top."}),
            dict(text="Aster can no longer be used by the traveller. This carrier restriction is independent of the coach supplement; "
                      "the arrival deadline and the fare rider remain unchanged.", docs={})]))

# ---- Forecast
def outlook(mode, delay):
    return (f"Weather outlook from the {mode} operator: a {delay}-minute delay to exposed departures is credibly possible. This is a "
            "forecast, not an actual delay. The final operating notice is due at minute 18. Both recovery departures are sheltered "
            "from this weather, but sales for them close at minute 14. A live hold stays usable after sales close until it expires. "
            "Each recovery hold costs USD 20 straight away; that USD 20 is credited toward the ticket price if the hold is confirmed, "
            "and an unused hold keeps the USD 20 charge. All other listed holds are free. Holding does not activate the emergency "
            "spending increase. Treat the deposit as part of current spending.")


def still_open(mode, delay):
    return dict(text=f"Outlook revised (version 2): the {mode} risk is still unresolved. This does not change any spending approval.",
                document_text=(f"The {delay}-minute delay is still only possible and remains uncertain. The actual operating notice "
                               "follows at minute 18. Recovery sales still close at minute 14; a live hold made earlier stays valid "
                               "until its stated expiry."))


def supplement_budget(mode, normal, raised, threshold):
    return (f"My ordinary total allowance is USD {normal}. Only when an observed operating notice reports an actual {mode} delay of at "
            f"least {threshold} minutes does it increase to USD {raised}. A forecast or a risk warning does not unlock the increase. "
            "Retained cancellation charges and any hotel charge count toward both ceilings, and once the condition has actually "
            "occurred no further permission is needed.")


FORECAST_ARRIVAL = "I have to be at the client by 11:15; the transfer from transport-guide counts."
CASES.append(base_variant("dev-17b13a1153", "stress-07-delay-refund-reworded", R2, dict(
    budget=supplement_budget("flight", 145, 190, 30), arrival=FORECAST_ARRIVAL), forecast=outlook("flight", 40),
    events=[still_open("flight", 40),
            dict(text="Operating result: exposed flight departures actually ran 40 minutes late. This is the realized delay; see the "
                      "current operating notice.",
                 forecast_text="Operating outcome observed at minute 18: flight delay 40 minutes. Unexposed recovery departures keep "
                               "their original arrival times.")]))
CASES.append(base_variant("dev-ae66140cb6", "stress-08-held-recovery-reworded", R3, dict(
    budget=supplement_budget("train", 155, 200, 35), arrival=FORECAST_ARRIVAL), forecast=outlook("train", 45), line_style="dash",
    events=[still_open("train", 45),
            dict(text="Actual operations: exposed train departures are on schedule. The delay that was warned about did not happen, so "
                      "the conditional supplement stays inactive.",
                 forecast_text="Observed result at minute 18: train delay 0 minutes. Unexposed recovery departures keep their "
                               "original arrival times.")]))
CASES.append(base_variant("dev-700f85cf1a", "stress-09-timed-delay-reworded", R1, dict(
    budget=supplement_budget("coach", 165, 210, 30), arrival=FORECAST_ARRIVAL), forecast=outlook("coach", 40),
    events=[still_open("coach", 40),
            dict(text="Coach operations update: the exposed coach departures are 40 minutes late. This is the realized delay; read the "
                      "current operating notice.",
                 forecast_text="Final observation at minute 18: coach delay 40 minutes. Unexposed recovery departures retain their "
                               "original arrival times.")]))
CASES.append(base_variant("travel-9f7c83790326d2761f54", "stress-13-service-window-reworded", R2, dict(
    budget="Normally my total allowance is USD 170. When actual operating information confirms a flight delay of at least thirty "
           "minutes, an emergency ceiling of USD 220 applies to payments completed by virtual minute 26 at the latest. After that "
           "window, new payments fall back to the USD 170 limit. A forecast does not open the emergency allowance. Retained charges "
           "and any hotel fee count in both amounts.",
    arrival="The client expects me by 11:05, transfer included. The emergency spending window does not move this appointment."),
    forecast=("Forecast: 60% chance of weather delays to exposed flight services, with a current delay estimate of 40 minutes. That "
              "estimate is not an observed operating delay; the real outcome may be harmless or may require a different service. "
              "The final operating report arrives at virtual minute 18. Recovery options whose sales cutoff is virtual minute 14 "
              "must be held before sales close; a live hold can still be confirmed after the cutoff until it expires. Its visible "
              "deposit is credited toward the ticket if confirmed and is otherwise kept."),
    events=[dict(text="Final operating report: exposed flight services ran with no delay at all (0 minutes). The major disruption "
                      "that was warned about did not happen; use this observed outcome to check the current booking. Sheltered "
                      "services keep their original arrival times.",
                 forecast_text="Operating result observed at virtual minute 18: flight delay 0 minutes. The forecast is resolved; "
                               "sheltered services are unchanged.")]))


# ---------------------------------------------------------------- structural variants (original wording otherwise)
def structural(source_id, new_id):
    c = copy.deepcopy(ALL[source_id])
    c["case_id"] = new_id
    return c


c = structural("dev-486fd97b7c", "stress-14-extra-linked-document")
c["documents"]["client-agenda"] = dict(id="client-agenda", title="Client visit agenda", version=1, related=[],
                                       text="Agenda for the visit: the registration desk opens at 08:30, the meeting runs until 12:00, "
                                            "and lunch at 11:40 is optional. This agenda does not change the arrival obligation.")
c["documents"]["arrival-contract"]["related"] = ["client-agenda"]
CASES.append(c)

c = structural("dev-2222f98c18", "stress-15-provider-notice")
c["events"].insert(0, dict(at=8, kind="provider_notice", changes={},
                           text="Provider notice: a confirmation reply may be lost even when the booking succeeded. Check the "
                                "booking status with the same request before trying another commitment."))
CASES.append(c)

c = structural("dev-0712f477b1", "stress-16-transport-update")
c["events"].insert(0, dict(at=10, kind="transport_update",
                           text="A road closure changed the onward transfers to the client, not the terminal arrival times. Read the "
                                "current transport-guide before choosing or keeping a replacement.",
                           changes=dict(transfer=dict(flight=30, train=20, coach=20),
                                        document_text="Add 30 minutes to terminal arrival for a flight and 20 minutes for a train "
                                                      "or coach. The result is arrival at the client, not terminal arrival.")))
CASES.append(c)

c = structural("dev-5f4a5e2291", "stress-17-hotel-bulletin-replaced")
c["events"].append(dict(at=6, kind="document_update",
                        text="The hotel replaced hotel-bulletin. Claims still pending must use the new procedure; claims already "
                             "accepted stand.",
                        changes=dict(waiver="disruption-letter", waiver_version=3,
                                     document_text="Claim evidence type disruption-letter, code proof-914301, version 3, before "
                                                   "virtual minute 30. A successful claim removes the USD 55 charge while "
                                                   "retaining the room.")))
CASES.append(c)

c = structural("dev-d1e8acd8cc", "stress-18-inline-carrier-ban")
BANNED = "Birch"
c["events"].append(dict(at=20, kind="user_update", changes=dict(avoid_carriers=[BANNED]),
                        text=f"One more change: please do not use {BANNED} for my outbound from now on. Everything else stays as it is."))
CASES.append(c)

c = structural("dev-17b13a1153", "stress-19-weather-watch-wording")
weather = next(e for e in c["events"] if e["kind"] == "weather_update")
weather["text"] = ("Dispatch resolved the current lead-outbound weather watch. Read the current report before handoff and inspect "
                   "booked arrivals; current trip restrictions and recovery closing times still apply.")
weather["changes"]["forecast_text"] = "Final report at minute 18: the exposed flight departures were delayed by 40 minutes."
CASES.append(c)


# ---------------------------------------------------------------- checks
def feasible_offers(case, at):
    world = world_for_case(copy.deepcopy(case), concurrency=3)
    world._advance(at)
    found = []
    for option in world._options.values():
        on_sale = option["inventory"] > 0 and option.get("available_from", 0) <= world.now < option["expires_at"]
        if not on_sale:
            continue
        facts = world._offer_facts(option)
        rules = world._rules
        spend = option["price"]  # a correct solver claims the waiver, which removes the hotel fee
        if (spend <= world._limit(option) and facts["meeting_arrival"] <= world._deadline(option)
                and (not rules["requires_step_free"] or option["step_free"]) and option["carrier"] not in rules["avoid_carriers"]):
            found.append(option["id"])
    return sorted(found)


def main():
    problems = 0
    for case in CASES:
        validate_case(case)
        source = next(s for s in ALL.values() if s["seed"] == case["seed"] and s["family"] == case["family"])
        times = sorted({0, *[e["at"] + 1 for e in case["events"]]})
        report = []
        for at in times:
            mine, theirs = feasible_offers(case, at), feasible_offers(source, at)
            same = "same" if mine == theirs else f"orig={len(theirs)}"
            report.append(f"t{at}:{len(mine)}({same})")
            if not mine and at <= 12:
                problems += 1
                report.append("NO FEASIBLE OFFER")
        print(f"{case['case_id']:38} {case['difficulty']:8} {' '.join(report)}")
    out = ROOT / "local_cases" / "stress_v1.json"
    out.write_text(json.dumps(CASES, indent=1, ensure_ascii=True), encoding="utf-8")
    print(f"\nwrote {len(CASES)} cases to {out}; problems={problems}")


main()
