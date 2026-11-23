"""EDITABLE: routing, memory, planning and the agent interaction loop.

Keep additional policy functions/classes here. Model calls use api.json/api.decide;
all actions must use the supplied world interface. Do not import the evaluator,
read future events, inspect _spec/_rules, or choose actions by case-ID lookup.
"""
from framework.fp_agents import run_travel_agent as supplied_agent, travel_route
from framework.contract_interpreter import (INSTRUCTIONS as CONTRACT_INSTRUCTIONS, compile_contract, make_schema,
                                            role_source_ids)
from framework.contract_policy import Controller, action
from .prompts import PROJECT_PARTS, PROJECT_PROMPT
from copy import deepcopy
import json
import re
from types import SimpleNamespace


def interpret_with_consent_references(api, settings, instructions, payload, schema, label):
    observation = {key: payload["observation"][key]
                   for key in ("virtual_minute", "tier", "notices", "operational_sources")}
    payload = dict(payload, observation=observation)
    notices = payload["observation"]["notices"]
    # shortcut: alias the standard consent format, extend coverage if other formats cause copying errors.
    token_pattern = r"\bconsent-[A-Za-z0-9]+(?:[-_][A-Za-z0-9]+)*\b"
    tokens = dict.fromkeys(token for notice in notices
                           for token in re.findall(token_pattern, notice["text"]))
    if not tokens or any("[CONSENT_REF_" in notice["text"] for notice in notices):
        return api.json(settings, instructions, payload, schema, label)

    references = {token: f"[CONSENT_REF_{index}]" for index, token in enumerate(tokens, 1)}
    payload = deepcopy(payload)
    for notice in payload["observation"]["notices"]:
        notice["text"] = re.sub(token_pattern, lambda match: references[match[0]], notice["text"])
    if previous := payload.get("previous"):
        facts = previous["facts"]
        facts["consent"] = references.get(facts["consent"], facts["consent"])
    instructions += (
        "\nA bracketed CONSENT_REF token stands for the literal code at that position. "
        "If the applicable approval uses one, copy the complete bracketed token "
        "into facts.consent. Determine approval scope and amendments as usual."
    )
    response = api.json(settings, instructions, payload, schema, label)
    codes = {reference: code for code, reference in references.items()}
    facts = response["facts"]
    selected = facts["consent"]
    reference = f'[{selected.strip().strip("[]")}]'
    return dict(response, facts=dict(facts, consent=codes.get(reference, selected)))


def resolve_observed_weather(payload, previous_packet):
    if previous_packet is None or not payload.get("previous"):
        return None
    notices = payload["observation"]["notices"]
    earlier = previous_packet["observation"]["notices"]
    if len(notices) != len(earlier) + 1 or notices[:-1] != earlier:
        return None
    event = notices[-1]
    if event["kind"] != "weather_update":
        return None
    forecast_id = "weather-forecast"
    documents = {source["id"]: source for source in payload["documents"]}
    forecast = documents.pop(forecast_id, None)
    unchanged = {source["id"]: source for source in previous_packet["documents"]
                 if source["id"] != forecast_id}
    earlier_forecast = next((source for source in previous_packet["documents"]
                             if source["id"] == forecast_id), None)
    if not forecast or not earlier_forecast or forecast["version"] <= earlier_forecast["version"] or documents != unchanged:
        return None
    sources = payload["observation"]["operational_sources"]
    if sources != previous_packet["observation"]["operational_sources"] or any(
        source["id"] == forecast_id for source in sources.values()
    ):
        return None
    offers = payload["offers"]
    previous = payload["previous"]
    if {offer["id"] for offer in offers} != previous["refund_terms"].keys():
        return None
    if any((offer.get("refund_contract_source") or {}).get("id") == forecast_id for offer in offers):
        return None

    # shortcut: recognize standalone operating reports; defer mixed or unfamiliar notices to the interpreter.
    report = re.fullmatch(
        r"Observed operating result at virtual minute (\d+): (flight|train|coach) delay (\d+) minutes\. "
        r"This resolves the forecast; sheltered services are unchanged\.",
        forecast["text"],
    )
    notice = re.fullmatch(
        r"The final operating report confirms an actual (\d+)-minute delay to exposed (flight|train|coach) services\. "
        r"(?:Use this observed disruption when checking the existing booking\.|"
        r"The warned major disruption has not occurred; use this observed outcome when checking the existing booking\.) "
        r"Sheltered services retain their original arrival times\.",
        event["text"],
    )
    if not report or not notice:
        return None
    minute, mode, delay = report.groups()
    if int(minute) != event["at"] or notice.groups() != (delay, mode):
        return None
    facts = deepcopy(previous["facts"])
    facts["weather"][mode] = int(delay)
    facts["forecasts"] = [row for row in facts["forecasts"] if row["mode"] != mode]
    return {
        "budget_limit": previous["budget_limit"],
        "arrival_deadline": previous["arrival_deadline"],
        "refund_groups": [{"offer_ids": [identifier], "retained": expression}
                          for identifier, expression in previous["refund_terms"].items()],
        "facts": facts,
    }


CLOCK = r"(?:[01]\d|2[0-3]):[0-5]\d"
MODE = r"flight|train|coach"
FARE_HEADER = (
    r"Base fare fields describe ordinary cancellation: these fee fares normally retain USD \d+\. "
    r"The following provider terms override that amount\. They are fixed when each ticket is confirmed; "
    r"the conditions are checked when cancellation actually completes\. Cancellation uses the outbound consent\. "
    r"A hold is not a confirmed replacement, and overlapping confirmed outbounds remain forbidden\.\n"
)


def clock_minutes(clock):
    hours, minutes = map(int, clock.split(":"))
    return 60 * hours + minutes


def compare(op, variable, value):
    return {"op": op, "left": {"var": variable}, "right": value}


def read_outlook(text):
    outlook = re.fullmatch(
        rf"The forecast gives a (\d+)% chance of weather delays to exposed ({MODE}) services\. "
        r"The current delay estimate is (\d+) minutes; this estimate is not an observed operating delay\. "
        r"The actual outcome may be harmless or may require a different service\. "
        r"A final operating report arrives at virtual minute (\d+)\. "
        r"Recovery options with a sales cutoff of virtual minute \d+ must be held before sales close\. "
        r"A live hold can be confirmed after the sales cutoff until its own expiry\. "
        r"Its visible deposit is credited toward the ticket if confirmed and otherwise remains charged\.",
        text,
    )
    if not outlook:
        return None
    probability, mode, delay, report = outlook.groups()
    return {"mode": mode, "delay": int(delay), "at": int(report), "probability": int(probability)}


def read_arrival(text):
    plain = re.fullmatch(
        rf"(?:The client needs me there|Reach the client) by ({CLOCK}), including the current transfer"
        r"(?: from the terminal)?\.",
        text,
    )
    if plain:
        return clock_minutes(plain[1])
    appointment = re.fullmatch(
        rf"Arrive at the client by ({CLOCK}), including the current transfer\. "
        r"The emergency spending window does not change the appointment\.",
        text,
    )
    if appointment:
        return clock_minutes(appointment[1])
    concession = re.fullmatch(
        rf"Please arrive at the client by ({CLOCK})\. I can accept ({CLOCK}) when the selected service is a ({MODE})\. "
        r"That concession is withdrawn for \3 tickets priced above USD (\d+): "
        r"those tickets must still get me there by \1\. These are client arrival times, so include the transfer\.",
        text,
    )
    if concession:
        default, exception, mode, maximum = concession.groups()
        return {"op": "if", "when": {"op": "and", "args": [
            compare("eq", "candidate.mode", mode),
            compare("le", "candidate.price", int(maximum)),
        ]}, "then": clock_minutes(exception), "else": clock_minutes(default)}
    return None


def read_spending_limit(text):
    fixed = re.fullmatch(
        rf"The approved total for this repair is USD (\d+), including retained charges and any hotel fee\. "
        rf"The later (?:{MODE}) arrival concession below does not increase this amount\.|"
        r"I approve total additional spending up to USD (\d+), including retained ticket charges and any hotel fee\.",
        text,
    )
    if fixed:
        return int(fixed[1] or fixed[2])
    emergency = re.fullmatch(
        r"My normal total allowance is USD (\d+)\. If actual operating information confirms a "
        rf"({MODE}) delay of at least (thirty|\d+) minutes, the emergency ceiling is USD (\d+) "
        r"for payments completed no later than virtual minute (\d+)\. After that service window, "
        r"new payments are again limited to USD \1\. A forecast is not enough to open the emergency allowance\. "
        r"Both amounts include retained charges and any hotel fee\.",
        text,
    )
    if emergency:
        normal, mode, threshold, ceiling, window = emergency.groups()
        delay = 30 if threshold == "thirty" else int(threshold)
        return {"op": "if", "when": {"op": "and", "args": [
            compare("ge", f"state.weather.{mode}", delay),
            compare("le", "state.now", int(window)),
        ]}, "then": int(ceiling), "else": int(normal)}
    quote = re.fullmatch(
        r"For this trip, a qualifying quote is a currently available step-free service, operated by any carrier "
        rf"other than ([\w -]+), that gets me to the client by ({CLOCK})\. "
        r"Use the cheapest such quote as the spending reference\. I approve that fare plus USD (\d+) "
        r"for the whole repair, with an absolute ceiling of USD (\d+)\. If no quote qualifies, the ceiling is USD (\d+)\. "
        r"This total includes the ticket, retained charges and any hotel amount still due; the USD \3 is not a second allowance\. "
        r"For these offer comparisons, currently available quotes include unheld inventory still on sale and the particular "
        r"option now being considered if your own live hold preserves it after sales close\. Other held options are not "
        r"automatically included in that quote set; a condition that calls for a live hold checks held options separately\.",
        text,
    )
    if not quote:
        return None
    excluded, time, add, cap, fallback = quote.groups()
    qualifying = {"op": "and", "args": [
        {"var": "item.step_free"},
        compare("ne", "item.carrier", excluded),
        compare("le", "item.meeting_arrival", clock_minutes(time)),
    ]}
    lowest = {"op": "minimum", "pool": "offers", "where": qualifying,
              "value": {"var": "item.price"}, "default": int(fallback)}
    return {"op": "if", "when": {"op": "exists", "pool": "offers", "where": qualifying},
            "then": {"op": "min", "args": [int(cap), {"op": "add", "args": [lowest, int(add)]}]},
            "else": int(fallback)}


def read_initial_contract(payload):
    notices = payload["observation"]["notices"]
    if payload["previous"] is not None or len(notices) != 1 or notices[0]["kind"] != "initial_request":
        return None
    # shortcut: compile complete supported document forms; defer unfamiliar wording or conflicting evidence.
    request = re.fullmatch(
        rf"Repair my cancelled outbound to [\w -]+\. Prefer ({MODE}) whenever a suitable \1 is affordable\. "
        r"I require step-free travel\. (?:All listed carriers are permitted\.|Do not use ([\w -]+)\. "
        r"All other listed carriers are permitted\.) Keep the existing hotel and my colleague's return unchanged, "
        r"and claim the hotel charge waiver\. Approval ([\w-]+) covers my outbound and its permitted cancellation, "
        r"subject to the spending conditions in ([\w-]+)\. Read ([\w-]+) for the binding arrival obligation, "
        r"([\w-]+) for transfers, and ([\w-]+) for actual cancellation refunds\. "
        r"A first confirmed replacement is required by virtual minute \d+\. "
        r"(?:Verify the booking before handing it over at or after minute \d+\.|"
        r"I may send partial changes later\. Keep checking current notices through minute \d+ and finish by minute \d+\.) "
        r"(?:Read weather-forecast before the recovery sales close\. The announced risk is uncertain; "
        r"a later operating notice will report what actually happened\. )?"
        r"Clock times and arrival minutes refer to local time after midnight; virtual minutes measure elapsed tool time\. "
        r"Spending authorization is checked when a charged action completes\. A later lower allowance does not revoke an earlier authorized payment\.",
        notices[0]["text"],
    )
    if not request:
        return None
    mode, excluded, consent, budget_id, arrival_id, transfer_id, fare_id = request.groups()
    documents = {source["id"]: source for source in payload["documents"]}
    expected = {budget_id, arrival_id, transfer_id, fare_id, "hotel-terms", "hotel-bulletin", "traveler-profile"}
    extra = set(documents) - expected
    outlook = None
    if extra == {"weather-forecast"}:
        outlook = read_outlook(documents["weather-forecast"]["text"])
        if outlook is None or "Read weather-forecast before the recovery sales close." not in notices[0]["text"]:
            return None
    elif extra:
        return None
    sources = payload["observation"]["operational_sources"]
    if any(sources.get(key) != {"id": source_id, "version": documents[source_id]["version"]}
           for key, source_id in (("budget_limit", budget_id), ("arrival_deadline", arrival_id))):
        return None
    offers = payload["offers"]
    fare_ref = {"id": fare_id, "version": documents[fare_id]["version"]}
    if not offers or any(offer.get("refund_contract_source") != fare_ref for offer in offers):
        return None
    profile = (
        f"Use a suitable {mode} if one is affordable. Keep step-free access. "
        "The colleague's separate return and our existing hotel are outside this request."
    )
    if documents["traveler-profile"]["text"] != profile + (f" Do not use {excluded}." if excluded else ""):
        return None
    transfer = re.fullmatch(r"Add (\d+) minutes to terminal arrival for flight, train or coach\. "
                            r"The result is arrival at the client, not terminal arrival\.", documents[transfer_id]["text"])
    waiver = re.fullmatch(r"Claim evidence type ([\w-]+), code ([\w-]+), version (\d+), before virtual minute \d+\. "
                          r"A successful claim removes the USD (\d+) charge while retaining the room\.", documents["hotel-bulletin"]["text"])
    fare = re.fullmatch(FARE_HEADER + r"(?:Cancellation retains USD (\d+) from the ticket price\. The balance is refunded\.|"
                        r"If a ticket is cancelled, the provider retains USD (\d+) and refunds the rest\.)",
                        documents[fare_id]["text"])
    refunds = ([{"offer_ids": [offer["id"] for offer in offers], "retained": int(fare[1] or fare[2])}]
               if fare else read_weather_refunds(payload))
    budget = read_spending_limit(documents[budget_id]["text"])
    arrival = read_arrival(documents[arrival_id]["text"])
    if not all((transfer, waiver)) or refunds is None or budget is None or arrival is None:
        return None
    hotel = f"Keep the room. Read the linked hotel-bulletin for the current evidence that removes the USD {waiver[4]} charge."
    if documents["hotel-terms"]["text"] != hotel or int(waiver[3]) != documents["hotel-bulletin"]["version"]:
        return None
    return {
        "budget_limit": budget, "arrival_deadline": arrival,
        "refund_groups": refunds,
        "facts": {
            "consent": consent, "preferred": mode, "requires_step_free": True, "avoid_carriers": [excluded] if excluded else [],
            "transfer": dict.fromkeys(("flight", "train", "coach"), int(transfer[1])),
            "weather": dict.fromkeys(("flight", "train", "coach"), 0),
            "forecasts": [outlook] if outlook else [],
            "waiver": {"topic": waiver[1], "code": waiver[2], "version": int(waiver[3])},
        },
    }


def read_spending_amendment(payload, previous_packet):
    prior = read_initial_contract(previous_packet) if previous_packet else None
    previous = payload.get("previous")
    if prior is None or previous is None or type(prior["budget_limit"]) is not int:
        return None
    now_observation = payload["observation"]
    old_observation = previous_packet["observation"]
    old_notices = old_observation["notices"]
    notices = now_observation["notices"]
    if notices[:len(old_notices)] != old_notices or len(notices) != len(old_notices) + 2:
        return None
    approval, restriction = notices[-2:]
    if approval["at"] != restriction["at"] or any(
        notice["kind"] != "user_update" for notice in (approval, restriction)
    ):
        return None
    supplement = re.fullmatch(
        rf"A limited ({MODE}) recovery supplement is now approved\. Read the revised spending approval; "
        r"the arrival obligation and fare conditions have not changed\.", approval["text"])
    carrier = re.fullmatch(
        rf"The traveller can no longer use ([\w -]+)\. This carrier restriction is separate from the "
        rf"({MODE}) spending supplement; the arrival deadline and fare rider stay unchanged\.", restriction["text"])
    if not supplement or not carrier or supplement[1] != carrier[2]:
        return None
    sources = now_observation["operational_sources"]
    old_sources = old_observation["operational_sources"]
    authority = sources["budget_limit"]
    source_id = authority["id"]
    if (authority["id"] != old_sources["budget_limit"]["id"]
            or authority["version"] <= old_sources["budget_limit"]["version"]
            or sources["arrival_deadline"] != old_sources["arrival_deadline"]):
        return None
    documents = {s["id"]: s for s in payload["documents"]}
    old_documents = {s["id"]: s for s in previous_packet["documents"]}
    spending = documents.pop(source_id, None)
    del old_documents[source_id]
    if spending is None or spending["version"] != authority["version"] or documents != old_documents:
        return None
    amended = re.fullmatch(
        rf"I can now stretch the total to USD (\d+) for a step-free ({MODE}) that gets me to the client by ({CLOCK}), "
        r"as long as earlier ticket cancellations have retained no more than USD (\d+)\. This replaces the USD (\d+) "
        r"ceiling only for a booking meeting all those conditions\. The ordinary USD \5 ceiling still covers every other choice\. "
        r"The appointment and the provider's refund terms stay as they were; the supplement is not another USD \1 on top\.",
        spending["text"],
    )
    old_offers = previous_packet["offers"]
    offers = payload["offers"]
    if not amended or amended[2] != supplement[1] or int(amended[5]) != prior["budget_limit"] or not offers:
        return None
    fare_source = old_offers[0]["refund_contract_source"]
    if any(offer.get("refund_contract_source") != fare_source for offer in offers):
        return None
    facts = deepcopy(previous["facts"])
    facts["avoid_carriers"] = list(dict.fromkeys([*facts["avoid_carriers"], carrier[1]]))
    cap, mode, arrival_time, fees, default = amended.groups()
    return {
        "budget_limit": {"op": "if", "when": {"op": "and", "args": [
            compare("eq", "candidate.mode", mode), {"var": "candidate.step_free"},
            compare("le", "candidate.meeting_arrival", clock_minutes(arrival_time)),
            compare("le", "state.retained_fees", int(fees)),
        ]}, "then": int(cap), "else": int(default)},
        "arrival_deadline": previous["arrival_deadline"],
        "refund_groups": [{"offer_ids": [offer["id"] for offer in offers],
                           "retained": prior["refund_groups"][0]["retained"]}],
        "facts": facts,
    }


def read_weather_refunds(payload):
    sources = {source["id"]: source for source in payload["documents"]}
    groups = {}
    for offer in payload["offers"]:
        reference = offer.get("refund_contract_source")
        source = sources.get(reference["id"]) if reference else None
        if source is None or reference["version"] != source["version"]:
            return None
        # shortcut: compile this complete provider clause; defer other refund text to the model.
        clause = re.fullmatch(
            FARE_HEADER + rf"Ordinary cancellation retains USD (\d+)\. An exposed ({MODE}) ticket receives "
            r"a full refund when cancellation completes by virtual minute (\d+) and the actual \2 delay is "
            r"at least (\d+|thirty) minutes\. Both requirements must be met\. Sheltered \2(?:s|es) and other "
            r"modes keep the ordinary charge, even during the disruption\.",
            source["text"],
        )
        if not clause:
            return None
        retained, mode, cutoff, threshold = clause.groups()
        eligible = offer["mode"] == mode and offer.get("weather_exposed") is True
        key = (int(retained), mode, int(cutoff), 30 if threshold == "thirty" else int(threshold)) if eligible else (int(retained),)
        groups.setdefault(key, []).append(offer["id"])

    result = []
    for key, identifiers in groups.items():
        expression = key[0]
        if len(key) > 1:
            retained, mode, cutoff, minimum = key
            expression = {"op": "if", "when": {"op": "and", "args": [
                compare("le", "state.now", cutoff),
                compare("ge", f"state.weather.{mode}", minimum),
            ]}, "then": 0, "else": retained}
        result.append({"offer_ids": identifiers, "retained": expression})
    return result if result else None


CONSENT_TOKEN = r"\bconsent-[A-Za-z0-9]+(?:[-_][A-Za-z0-9]+)*\b"
TRAVELER_FACTS = ("preferred", "requires_step_free", "avoid_carriers")
WEATHER_FACTS = ("weather", "forecasts")
FACT_ORDER = (*TRAVELER_FACTS, "transfer", "waiver", *WEATHER_FACTS)
UPDATE_KINDS = {"user_update", "forecast_update", "weather_update"}
NOTICE_TOPICS = (
    ("budget_limit", r"\b(?:spend|allowance|ceiling|budget|USD|supplement|payment)"),
    ("arrival_deadline", r"\b(?:arriv|deadline|appointment|meeting|registration|check-in|client by)"),
    ("transfer", r"\btransfer"),
    ("waiver", r"\b(?:hotel|waiver|bulletin)"),
)
TRAVELER_TOPIC = (r"\b(?:carriers?|airlines?|operators?|step[- ]free|access\w*|wheelchair|prefer\w*|avoid\w*|"
                  r"exclud\w*|permitted|no longer (?:use|fly|take|travel)|(?:cannot|can't|must not|may not) "
                  r"(?:use|fly|take|travel)|rail|flying)\b")
CLOCK_TOPIC = r"\b(?:[01]?\d|2[0-3]):[0-5]\d\b|\bneeds? me\b"
CONTINUES = re.compile(r"\b(?:continues?|unchanged|unaffected|remains?|stays?|stand|still appl(?:y|ies)|keep|retain|"
                       r"(?:have|has|had) not (?:been )?changed|not changed|as (?:they|it) (?:was|were))\b", re.IGNORECASE)
CHANGE_WORD = re.compile(r"\b(?:now|new|newly|replac\w*|no longer|only|instead|mov\w*|chang\w*|reduc\w*|rais\w*|"
                         r"increas\w*|lower\w*|extend\w*|withdraw\w*|revis\w*|updat\w*|amend\w*|except\w*)\b",
                         re.IGNORECASE)
CLAUSE_SPLIT = re.compile(r"[;!?]|[.:](?!\d)|\b(?:but|while|however|although|except)\b", re.IGNORECASE)


def restates_only(clause):
    """A clause that says a rule continues, with no figure and no change word outside that statement."""
    return bool(CONTINUES.search(clause)) and not re.search(r"\d", clause) \
        and not CHANGE_WORD.search(CONTINUES.sub(" ", clause))


def update_topics(text, carriers):
    """Contract keys (and 'traveler') that some clause of an update may amend."""
    topics = set()
    patterns = (*NOTICE_TOPICS, ("arrival_deadline", CLOCK_TOPIC), ("traveler", TRAVELER_TOPIC))
    for clause in CLAUSE_SPLIT.split(text):
        if any(re.search(rf"\b{re.escape(carrier)}\b", clause) for carrier in carriers):
            topics.add("traveler")
        if restates_only(clause):
            continue
        topics.update(key for key, pattern in patterns if re.search(pattern, clause, re.IGNORECASE))
    return topics


OFFER_KEYS = ("id", "mode", "price", "carrier", "step_free", "arrival_minute", "weather_exposed",
              "available_from", "expires_at", "hold_fee_usd", "change_policy", "cancel_fee_usd")


WEATHER_EVENT_KINDS = {"forecast_update", "weather_update"}
STAMP_NUMBER = re.compile(r"(?:\bminute|\bversion)\s+$", re.IGNORECASE)
DELAY_PATTERNS = (re.compile(r"\b(\d+)[- ]minutes?\s+delay", re.IGNORECASE),
                  re.compile(r"\bdelay(?:ed)?\s+(?:of\s+|by\s+)?(\d+)\s+minutes?\b", re.IGNORECASE))
ON_TIME = re.compile(r"\bon time\b", re.IGNORECASE)
HEDGE = re.compile(r"\b(?:possible|possibly|may|might|could|estimated?|uncertain|unresolved|expected|likely|chance|"
                   r"risk|preliminary|provisional|so far|further|next report|at least|up to|forecasts? (?:a|an))\b|%",
                   re.IGNORECASE)
REALIZED = re.compile(r"\b(?:actual|actually|observed|realized|realised|final operating|operating (?:result|outcome|report)|"
                      r"confirms?|confirmed)\b", re.IGNORECASE)
STILL_OPEN = re.compile(r"\b(?:remains?|still|is still)\s+(?:uncertain|unresolved|open|possible)\b", re.IGNORECASE)
SETTLED = re.compile(r"\b(?:did not|has not|have not|not occur|on time|resolved|realized|realised|confirms?|confirmed|"
                     r"delayed by|observed|cancelled|canceled)\b", re.IGNORECASE)


def mentioned_modes(texts):
    return {mode for mode in ("flight", "train", "coach")
            for text in texts if re.search(rf"\b{mode}(?:e?s)?\b", text, re.IGNORECASE)}


def free_numbers(text):
    """Numbers that are neither clock stamps (minute N) nor document versions."""
    return [(match.start(), int(match[0])) for match in re.finditer(r"\d+", text)
            if not STAMP_NUMBER.search(text[:match.start()])]


def unversioned_numbers(text):
    return [int(match[0]) for match in re.finditer(r"\d+", text)
            if not re.search(r"\bversion\s+$", text[:match.start()], re.IGNORECASE)]


def reported_delay(text):
    """The single realized delay a report states, or None when any figure is unexplained."""
    delays = {}
    for pattern in DELAY_PATTERNS:
        for match in pattern.finditer(text):
            delays[match.start(1)] = int(match[1])
    if any(position not in delays for position, _ in free_numbers(text)):
        return None
    values = set(delays.values()) | ({0} if ON_TIME.search(text) else set())
    return values.pop() if len(values) == 1 else None


def read_weather_event(new_notices, forecast, earlier_forecast, facts):
    """Read a pure forecast or operating update locally; None defers it to the interpreter.

    Two forms are supported in any wording: a forecast that stays open with no new figure,
    and one realized delay for a single forecast mode. Anything else goes to the model.
    """
    if not new_notices or any(notice["kind"] not in WEATHER_EVENT_KINDS for notice in new_notices):
        return None
    announced = {row["mode"] for row in facts.get("forecasts") or []}
    texts = [notice["text"] for notice in new_notices]
    if forecast is not None and forecast != earlier_forecast:
        texts.append(forecast["text"])
    modes = mentioned_modes(texts)
    if not announced or not modes <= announced:
        return None
    joined = " ".join(texts)
    if STILL_OPEN.search(joined) and not SETTLED.search(joined):
        # An open forecast may restate earlier figures, but any new number could be a changed estimate or report time.
        known = set(unversioned_numbers(earlier_forecast["text"])) if earlier_forecast else set()
        if all(value in known for text in texts for value in unversioned_numbers(text)):
            return {"weather": deepcopy(facts["weather"]), "forecasts": deepcopy(facts["forecasts"])}
        return None
    if len(modes) != 1 or HEDGE.search(joined) or not REALIZED.search(joined):
        return None
    delays = {reported_delay(text) for text in texts}
    if None in delays or len(delays) != 1:
        return None
    mode = modes.pop()
    weather = dict(facts["weather"], **{mode: delays.pop()})
    return {"weather": weather, "forecasts": [deepcopy(row) for row in facts["forecasts"] if row["mode"] != mode]}


def strict_object(properties):
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def read_ticket_refund(clause):
    ordinary = re.fullmatch(r"[Oo]rdinary cancellation retains USD (\d+); there is no additional exception\.", clause)
    if ordinary:
        return int(ordinary[1])
    deadline = re.fullmatch(r"Cancellation completed by (?:virtual )?minute (\d+), inclusive, receives a full refund\. "
                            r"Later cancellation retains USD (\d+)\.", clause)
    if deadline:
        return {"op": "if", "when": compare("le", "state.now", int(deadline[1])), "then": 0, "else": int(deadline[2])}
    reduced = re.fullmatch(r"Cancellation completed by (?:virtual )?minute (\d+) retains USD (\d+), otherwise USD (\d+)\.",
                           clause)
    if reduced:
        return {"op": "if", "when": compare("le", "state.now", int(reduced[1])),
                "then": int(reduced[2]), "else": int(reduced[3])}
    return None


def split_ticket_terms(text):
    header = re.match(FARE_HEADER, text)
    if not header:
        return None
    terms = {}
    for line in text[header.end():].split("\n"):
        ticket = re.fullmatch(r"Ticket ([\w-]+): (.+)", line)
        if not ticket or ticket[1] in terms:
            return None
        terms[ticket[1]] = ticket[2]
    return text[:header.end()], terms


def read_ticket_refunds(offers, documents):
    known, pending = {}, {}
    for offer in offers:
        reference = offer.get("refund_contract_source") or {}
        source = documents.get(reference.get("id"))
        if source is None or source["version"] != reference.get("version"):
            return None
        split = split_ticket_terms(source["text"])
        expression = read_ticket_refund(split[1][offer["id"]]) if split and offer["id"] in split[1] else None
        if expression is None:
            pending.setdefault(source["id"], []).append(offer["id"])
        else:
            known[offer["id"]] = expression
    return known, pending


def read_local_facts(request, documents):
    facts, asks = {}, set()
    profile = re.fullmatch(
        rf"Use a suitable ({MODE}) if one is affordable\. Keep step-free access\. The colleague's separate return "
        r"and our existing hotel are outside this request\.(?: Do not use ([\w -]+)\.)?",
        documents.get("traveler-profile", {}).get("text", ""))
    prefer = re.search(rf"\bPrefer ({MODE}) whenever a suitable \1 is affordable\.", request)
    excluded = re.search(r"\bDo not use ([\w -]+)\. All other listed carriers are permitted\.", request)
    if (profile and prefer and prefer[1] == profile[1] and "I require step-free travel." in request
            and (excluded[1] if excluded else None) == profile[2]
            and (excluded or "All listed carriers are permitted." in request)):
        facts.update(preferred=profile[1], requires_step_free=True, avoid_carriers=[profile[2]] if profile[2] else [])
    else:
        asks.update(TRAVELER_FACTS)
    transfer = re.fullmatch(r"Add (\d+) minutes to terminal arrival for flight, train or coach\. "
                            r"The result is arrival at the client, not terminal arrival\.",
                            documents.get("transport-guide", {}).get("text", ""))
    if transfer:
        facts["transfer"] = dict.fromkeys(("flight", "train", "coach"), int(transfer[1]))
    else:
        asks.add("transfer")
    bulletin = documents.get("hotel-bulletin")
    waiver = bulletin and re.fullmatch(
        r"Claim evidence type ([\w-]+), code ([\w-]+), version (\d+), before virtual minute \d+\. "
        r"A successful claim removes the USD (\d+) charge while retaining the room\.", bulletin["text"])
    hotel = documents.get("hotel-terms", {}).get("text")
    if waiver and int(waiver[3]) == bulletin["version"] and hotel == (
            f"Keep the room. Read the linked hotel-bulletin for the current evidence that removes the USD {waiver[4]} charge."):
        facts["waiver"] = {"topic": waiver[1], "code": waiver[2], "version": int(waiver[3])}
    else:
        asks.add("waiver")
    forecast = documents.get("weather-forecast")
    outlook = read_outlook(forecast["text"]) if forecast else None
    if forecast is None or outlook:
        facts.update(weather=dict.fromkeys(("flight", "train", "coach"), 0), forecasts=[outlook] if outlook else [])
    else:
        asks.update(WEATHER_FACTS)
    return facts, asks


SCOPED_INTRO = (
    "You compile currently observed travel contract fields into the typed object required by the response schema. "
    "You do not grade, choose an offer, or infer future events. Interpret ordinary English scope, exceptions, "
    "amendments and inequalities exactly. Preserve unamended conditions. The current authoritative source versions "
    "supersede earlier text only for their stated scope. A forecast is a possibility, never realized weather. "
    "This request asks only for the keys in its schema; every other field is already compiled, and unrelated "
    "documents and offers are omitted."
)
FACT_NOTES = {
    "preferred": "preferred: the preferred mode.",
    "requires_step_free": "requires_step_free: whether step-free access is required.",
    "avoid_carriers": "avoid_carriers: excluded carrier names. Ordinary access/carrier facts apply to the current trip.",
    "transfer": "transfer: minutes per mode added to terminal arrival to reach the client.",
    "waiver": "waiver: topic, code and version of the current hotel bulletin's actual evidence, not archived examples.",
    "weather": "weather: realized delay minutes per mode only, zero before realization.",
    "forecasts": ("forecasts: explicitly announced possible weather delays. Its at is the virtual minute of the "
                  "upcoming final operating report or uncertainty resolution, not the forecast's issue/revision time "
                  "or a backup sales cutoff. Use null for an unstated report time, delay or probability."),
}
EXPRESSION_NOTES = (
    "Expressions use the schema's forms; if branches short-circuit; 'in' requires a list on the right; ordering "
    "requires numbers. exists and minimum bind item to each pool object without changing outer candidate/booking; "
    "minimum returns the least value over matching items, else its default.\n"
    "candidate is the proposed offer or hold at purchase and the active booking when checking arrival; booking is "
    "empty before purchase. At cancellation both are the cancelled booking. now is action COMPLETION minute. "
    "meeting_arrival is terminal arrival plus current transfer. Missing optional object fields are null. offers is "
    "current unheld on-sale inventory plus a candidate's valid held offer; holds is all live holds. State amounts are "
    "actual current ledger amounts; retained_fees means cancellation retention only. Quoted fare price already "
    "includes any reservation deposit credited when confirmed."
)
EXPRESSION_RULES = (
    "Do not encode a preferred/optimal offer ID, read case IDs as clues, guess hidden schedules, translate conditions "
    "into unexplained booleans, or return prose instead of expressions. Keep every threshold and exception inside its "
    "proper conditional scope. Compile from source text, using previous interpretation only to preserve facts not "
    "amended by current evidence."
)
REFUND_RULES = (
    "Reference offer IDs only to map refund expressions to observed tickets. Base numeric change_policy/cancel_fee_usd "
    "are ordinary terms; conditional prose overrides them. For ordinary fee fares with no exceptions the refund "
    "expression is the numeric base retention; flexible is 0 and locked is null."
)
CEILING_RULE = "All monetary ceilings are total spending, unless the prose explicitly compares prices inside a condition."


def scoped_instructions(instructions, keys, fact_keys):
    """Instructions for only the requested keys; the strict schema already fixes the expression grammar."""
    if instructions != CONTRACT_INSTRUCTIONS + "\n" + PROJECT_PROMPT:
        return instructions
    outputs, ceiling = CONTRACT_INSTRUCTIONS.split("\n\nOutput object keys:\n", 1)[1].split("\n\n")[:2]
    key_lines = {line.split(":")[0]: line for line in outputs.split("\n")}
    lines = [key_lines[key] for key in keys]
    if fact_keys:
        lines.append("facts: " + " ".join(FACT_NOTES[key] for key in fact_keys))
    parts = [SCOPED_INTRO, "Output object keys:\n" + "\n".join(lines)]
    if "budget_limit" in keys:
        parts.append(ceiling)
    if keys:
        rules = [EXPRESSION_RULES]
        rules += [REFUND_RULES] if "refund_groups" in keys else []
        rules += [CEILING_RULE] if "budget_limit" in keys else []
        parts += [EXPRESSION_NOTES, " ".join(rules)]
    project = ["intro"] + (["waiver"] if "waiver" in fact_keys else []) + ["amendments"]
    project += ["exceptions"] if keys else []
    parts.append("\n".join(PROJECT_PARTS[name] for name in project))
    return "\n\n".join(parts)


def compile_partially(api, settings, instructions, payload, label, previous_packet):
    """Compile recognized or unchanged fields locally and ask the model only for the rest."""
    notices = payload["observation"]["notices"]
    documents = {source["id"]: source for source in payload["documents"]}
    sources = payload["observation"]["operational_sources"]
    offers = payload["offers"]
    previous = payload.get("previous")
    budget_id, arrival_id = sources["budget_limit"]["id"], sources["arrival_deadline"]["id"]
    fare_ids = {(offer.get("refund_contract_source") or {}).get("id") for offer in offers}
    known_ids = {budget_id, arrival_id, "traveler-profile", "transport-guide", "hotel-terms", "hotel-bulletin",
                 "weather-forecast"} | fare_ids
    if not offers or None in fare_ids or not set(documents) <= known_ids:
        return None
    asks, refunds = set(), {}
    contract = {}
    if previous is None:
        if len(notices) != 1 or notices[0]["kind"] != "initial_request":
            return None
        tokens = set(re.findall(CONSENT_TOKEN, notices[0]["text"]))
        if len(tokens) != 1:
            return None
        facts, asks = read_local_facts(notices[0]["text"], documents)
        facts["consent"] = tokens.pop()
        for key, source_id, reader in (("budget_limit", budget_id, read_spending_limit),
                                       ("arrival_deadline", arrival_id, read_arrival)):
            value = reader(documents[source_id]["text"]) if source_id in documents else None
            if value is None:
                asks.add(key)
            contract[key] = value
        pending_offers = offers
    else:
        if previous_packet is None or "refund_terms" not in previous:
            return None
        old_notices = previous_packet["observation"]["notices"]
        new = notices[len(old_notices):]
        if notices[:len(old_notices)] != old_notices or any(
                notice["kind"] not in UPDATE_KINDS or re.search(CONSENT_TOKEN, notice["text"]) for notice in new):
            return None
        old_documents = {source["id"]: source for source in previous_packet["documents"]}
        changed = {source_id for source_id in set(documents) | set(old_documents)
                   if documents.get(source_id) != old_documents.get(source_id)}
        old_sources = previous_packet["observation"]["operational_sources"]
        if changed - known_ids:
            return None
        updates = " ".join(notice["text"] for notice in new if notice["kind"] == "user_update")
        if updates:
            if not changed:
                return None
            carriers = {offer["carrier"] for offer in offers if offer.get("carrier")}
            carriers |= set(previous["facts"].get("avoid_carriers") or [])
            topics = update_topics(updates, carriers)
            for source_id in changed - {"weather-forecast"}:
                if source_id in documents and "traveler" in update_topics(documents[source_id]["text"], carriers):
                    topics.add("traveler")
            asks.update(TRAVELER_FACTS if "traveler" in topics else ())
            asks.update(topics - {"traveler"})
        if any(notice["kind"] != "user_update" for notice in new) or "weather-forecast" in changed:
            asks.update(WEATHER_FACTS)
        for key, source_id in (("budget_limit", budget_id), ("arrival_deadline", arrival_id)):
            if source_id in changed or sources[key] != old_sources.get(key):
                asks.add(key)
            contract[key] = previous[key]
        if "traveler-profile" in changed:
            asks.update(TRAVELER_FACTS)
        if "transport-guide" in changed:
            asks.add("transfer")
        if changed & {"hotel-terms", "hotel-bulletin"}:
            asks.add("waiver")
        facts = deepcopy(previous["facts"])
        if asks & set(WEATHER_FACTS) and changed <= {"weather-forecast"}:
            weather = read_weather_event(new, documents.get("weather-forecast"),
                                         old_documents.get("weather-forecast"), facts)
            if weather is not None:
                facts.update(weather)
                asks -= set(WEATHER_FACTS)
        old_references = {offer["id"]: offer.get("refund_contract_source") for offer in previous_packet["offers"]}
        pending_offers = []
        for offer in offers:
            reference = offer["refund_contract_source"]
            if (offer["id"] in previous["refund_terms"] and old_references.get(offer["id"]) == reference
                    and reference["id"] not in changed):
                refunds[offer["id"]] = deepcopy(previous["refund_terms"][offer["id"]])
            else:
                pending_offers.append(offer)
    parsed = read_ticket_refunds(pending_offers, documents)
    if parsed is None:
        return None
    local, pending = parsed
    refunds.update(local)
    pending_ids = [identifier for identifiers in pending.values() for identifier in identifiers]
    expression_keys = [key for key in ("budget_limit", "arrival_deadline") if key in asks]
    expression_keys += ["refund_groups"] if pending_ids else []
    fact_keys = [key for key in FACT_ORDER if key in asks]

    if expression_keys or fact_keys:
        wanted = set()
        if "budget_limit" in asks:
            wanted.add(budget_id)
        if "arrival_deadline" in asks:
            wanted |= {arrival_id, "transport-guide"}
        if asks & set(TRAVELER_FACTS):
            wanted.add("traveler-profile")
        if "transfer" in asks:
            wanted.add("transport-guide")
        if "waiver" in asks:
            wanted |= {"hotel-terms", "hotel-bulletin"}
        if asks & set(WEATHER_FACTS):
            wanted.add("weather-forecast")
        scoped_documents = [deepcopy(source) for source in payload["documents"]
                            if source["id"] in wanted and source["id"] not in pending]
        for source_id, identifiers in pending.items():
            source = deepcopy(documents[source_id])
            split = split_ticket_terms(source["text"])
            if split:
                header, terms = split
                source["text"] = header + "\n".join(f"Ticket {identifier}: {terms[identifier]}" for identifier in identifiers)
            scoped_documents.append(source)
        prior = {key: previous[key] for key in ("budget_limit", "arrival_deadline") if previous and key in asks}
        if previous and fact_keys:
            prior["facts"] = {key: previous["facts"][key] for key in fact_keys}
        scoped = {
            "observation": {key: payload["observation"][key]
                            for key in ("virtual_minute", "tier", "notices", "operational_sources")},
            "documents": scoped_documents,
            "offers": [{key: offer[key] for key in OFFER_KEYS if key in offer}
                       for offer in offers if offer["id"] in pending_ids],
            "previous": prior or None,
        }
        full = make_schema([offer for offer in offers if offer["id"] in pending_ids] or offers)
        properties = {key: deepcopy(full["properties"][key]) for key in expression_keys}
        if fact_keys:
            properties["facts"] = strict_object({key: deepcopy(full["properties"]["facts"]["properties"][key])
                                                 for key in fact_keys})
        schema = strict_object(properties)
        if expression_keys:
            schema["$defs"] = deepcopy(full["$defs"])
        response = api.json(settings, scoped_instructions(instructions, expression_keys, fact_keys),
                            scoped, schema, label)
        contract.update({key: response[key] for key in ("budget_limit", "arrival_deadline") if key in response})
        facts.update(response.get("facts", {}))
        for group in response.get("refund_groups", []):
            for identifier in group["offer_ids"]:
                if identifier in refunds or identifier not in pending_ids:
                    return None
                refunds[identifier] = deepcopy(group["retained"])
    if set(refunds) != {offer["id"] for offer in offers}:
        return None
    groups = {}
    for identifier, expression in refunds.items():
        groups.setdefault(json.dumps(expression, sort_keys=True), {"offer_ids": [], "retained": expression})
        groups[json.dumps(expression, sort_keys=True)]["offer_ids"].append(identifier)
    return {"budget_limit": contract["budget_limit"], "arrival_deadline": contract["arrival_deadline"],
            "refund_groups": list(groups.values()), "facts": facts}


def bind_free_items(expression, inside=False, root="booking"):
    """Rename item.* outside exists/minimum to the only ticket in scope.

    No pool object is bound there: in a refund rule that ticket is the cancelled booking, and in a spending or
    arrival rule it is the candidate being purchased or checked.
    """
    if isinstance(expression, list):
        return [bind_free_items(value, inside, root) for value in expression]
    if not isinstance(expression, dict):
        return expression
    if expression.get("op") in ("exists", "minimum"):
        return {key: bind_free_items(value, inside or key in ("where", "value"), root) for key, value in expression.items()}
    variable = expression.get("var")
    if not inside and set(expression) == {"var"} and isinstance(variable, str) and variable.startswith("item."):
        return {"var": root + "." + variable[len("item."):]}
    return {key: bind_free_items(value, inside, root) for key, value in expression.items()}


def mentions(expression, *roots):
    if isinstance(expression, dict):
        return (isinstance(expression.get("var"), str) and expression["var"].split(".")[0] in roots) or any(
            mentions(value, *roots) for value in expression.values())
    return isinstance(expression, list) and any(mentions(value, *roots) for value in expression)


def is_liveness_test(expression):
    """Expiry-versus-now or a status test on item: always settled inside the live-holds pool."""
    if not isinstance(expression, dict):
        return False
    sides = {json.dumps(expression.get("left")), json.dumps(expression.get("right"))}
    if expression.get("op") in ("lt", "le", "gt", "ge"):
        return sides == {json.dumps({"var": "item.expires_at"}), json.dumps({"var": "state.now"})}
    return (expression.get("op") in ("eq", "ne", "in") and json.dumps({"var": "item.status"}) in sides)


def price_minimums(expression, in_holds=False):
    """Normalize two degenerate quantifier forms.

    A minimum whose properly bound filter uses item but whose value is a constant means the item's price (fares).
    Inside the holds pool every item is a live hold, so an expiry-versus-now comparison there is redundant; an
    inverted one would wrongly require an expired hold, so it is replaced by true.
    """
    if isinstance(expression, list):
        return [price_minimums(value, in_holds) for value in expression]
    if not isinstance(expression, dict):
        return expression
    if in_holds and is_liveness_test(expression):
        return True
    pool_holds = expression.get("op") in ("exists", "minimum") and expression.get("pool") == "holds"
    result = {key: price_minimums(value, pool_holds if key in ("where", "value") else in_holds)
              for key, value in expression.items()}
    if (result.get("op") == "minimum" and mentions(result.get("where"), "item")
            and not mentions(result.get("value"), "item", "candidate", "booking")):
        result["value"] = {"var": "item.price"}
    return result


def bind_refund_items(result):
    if not isinstance(result, dict):
        return result
    result = dict(result, **{key: price_minimums(bind_free_items(result[key], root="candidate"))
                             for key in ("budget_limit", "arrival_deadline") if key in result})
    if not isinstance(result.get("refund_groups"), list):
        return result
    groups = [dict(group, retained=price_minimums(bind_free_items(group["retained"])))
              if isinstance(group, dict) and "retained" in group else group for group in result["refund_groups"]]
    return dict(result, refund_groups=groups)


WAIVER_TYPE = re.compile(r"\b[a-z]+(?:-[a-z]+)*-(?:reference|letter|receipt|notice|record|confirmation)\b")
SUPERSEDED_EVIDENCE = re.compile(r"\b(?:archive|archived|withdrawn|previous|former|earlier|old|last year|another room|"
                                 r"no longer|expired|example)\b", re.IGNORECASE)
SELLOUT_WARNING = re.compile(r"\b(trip-[\w-]*\w)\b[^.]*?\b(?:virtual )?minute (\d+)", re.IGNORECASE)


def bulletin_waiver(source):
    """Claim arguments when a bulletin names exactly one evidence type and proof code; otherwise None."""
    if not source:
        return None
    text = source["text"]
    codes = set(re.findall(r"\bproof-[\w-]*\w", text))
    types = set(WAIVER_TYPE.findall(text))
    versions = {int(value) for value in re.findall(r"\bversion\s+(\d+)", text, re.IGNORECASE)}
    if len(codes) != 1 or len(types) != 1 or versions - {source["version"]} or SUPERSEDED_EVIDENCE.search(text):
        return None
    return dict(topic=types.pop(), code=codes.pop(), version=source["version"])


def waiver_key(waiver):
    return (waiver.get("topic"), waiver.get("code"), waiver.get("version"))


class TimelyController(Controller):
    """The framework planner with faster first service; offer choice, budgets and refunds are unchanged.

    With three tool slots, the supplied boot reads every source (6 minutes), then claims the waiver alone
    (2 minutes), then holds and confirms. Any notice before minute 8 adds a 2-minute refresh, so the first
    confirmation lands after the minute-12 deadline, and a Forecast recovery hold misses its sales cutoff.
    This controller (1) claims during the boot reads when the bulletin evidence is unambiguous, using the slot
    those reads leave idle; (2) otherwise claims and holds the first planned booking in one batch, planning as
    if the claim succeeds; (3) retries a failed or superseded claim with the current interpreted evidence; and
    (4) treats a warned sellout minute as that offer's sales cutoff, so preparation holds it in time.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.claimed = set()

    def batch(self, actions):
        results = super().batch(actions)
        # A stock warning names when unheld inventory disappears; plan as if sales close then.
        for notice in self.world.observe()["notices"]:
            if notice["kind"] == "stock_update":
                for identifier, minute in SELLOUT_WARNING.findall(notice["text"]):
                    if identifier in self.offers:
                        self.offers[identifier]["expires_at"] = min(self.offers[identifier]["expires_at"], int(minute))
        return results

    def claim(self, waiver):
        self.claimed.add(waiver_key(waiver))
        return action("claim", topic=waiver["topic"], code=waiver["code"], version=waiver["version"])

    def refresh(self, initial=False):
        if not initial:
            return super().refresh()
        # As supplied: hotel-terms first, because it links the bulletin into the catalog.
        observation = self.world.observe()
        first = [action("search")]
        if any(source["id"] == "hotel-terms" for source in observation["source_catalog"]):
            first.append(action("read", id="hotel-terms"))
        spend_source = observation["operational_sources"]["budget_limit"]["id"]
        if spend_source != "hotel-terms":
            first.append(action("read", id=spend_source))
        self.batch(first)
        # Then the bulletin leads the next round, so the round after it can carry the claim.
        observation = self.world.observe()
        pending = sorted((action("read", id=source["id"]) for source in observation["source_catalog"]
                          if source["id"] not in self.documents or self.documents[source["id"]]["version"] != source["version"]),
                         key=lambda row: row["arguments"]["id"] != "hotel-bulletin")
        if pending:
            self.batch(pending[:3])
        rest = pending[3:]
        waiver = bulletin_waiver(self.documents.get("hotel-bulletin"))
        if waiver and self.world.observe()["hotel_fee"] and len(rest) % 3:
            rest.insert(0, self.claim(waiver))  # fills a slot the remaining reads leave idle
        if rest:
            self.batch(rest)
        self.interpret_observed()

    def interpret_observed(self):
        """The supplied refresh after its first batch: read remaining changes, interpret, bind purchased terms."""
        while not self.world.finished:
            observation = self.world.observe()
            pending = [action("read", id=source["id"]) for source in observation["source_catalog"]
                       if source["id"] not in self.documents or self.documents[source["id"]]["version"] != source["version"]]
            if not pending:
                break
            self.batch(pending)
        observation = self.world.observe()
        payload_observation = deepcopy(observation)
        payload_observation.pop("case_id", None)
        payload = dict(observation=payload_observation, documents=deepcopy(list(self.documents.values())),
                       offers=deepcopy(list(self.offers.values())), previous=deepcopy(self.program))
        if self.program is None or self.refresh_context:
            self.program = self.interpret(payload)
            self.interpreted_documents = deepcopy(self.documents)
        for identifier in self.sale_ids:
            self.offer_weather[identifier] = deepcopy(self.facts["weather"])
        self.revision = observation["revision"]
        if self.program is None:
            return
        for booking in self.world.observe()["bookings"]:
            if booking.get("status") != "confirmed" or booking.get("kind") != "transport":
                continue
            if self.booked_programs.get(booking["id"]) is not None:
                continue
            reference = booking.get("refund_contract_source", {})
            source = self.interpreted_documents.get(reference.get("id"))
            if source and source["version"] == reference.get("version"):
                self.booked_programs[booking["id"]] = deepcopy(self.program["refund_terms"].get(booking["option_id"]))
                self.booked_evidence[booking["id"]] = dict(purchased_source=deepcopy(reference),
                                                           read_source=deepcopy(source), interpreted_version_matches=True)

    def recovery_opportunity(self, observation, booking):
        """The supplied prepare() choice of one affordable recovery, without deferral and without the hold call."""
        opportunities = []
        for forecast in self.facts["forecasts"]:
            when, delay = forecast.get("at"), forecast.get("delay")
            if type(when) not in (int, float) or type(delay) not in (int, float) or when <= self.world.now:
                continue
            scenario = dict(self.facts["weather"], **{forecast["mode"]: delay})
            if self.keep_valid(observation, booking, weather=scenario, at=when):
                continue
            if any(hold["status"] == "held" and hold["expires_at"] > when + 4
                   and (candidate := self.offers.get(hold["option_id"]))
                   and self.purchase_plan(observation, candidate, booking, weather=scenario, at=when) is not None
                   for hold in observation["holds"]):
                continue
            for offer in self.candidates(observation):
                if offer["id"] == booking["option_id"]:
                    continue
                if any(hold["option_id"] == offer["id"] and hold["status"] == "held" and hold["expires_at"] > when + 4
                       for hold in observation["holds"]):
                    continue
                if offer["expires_at"] > when + 1 or self.world.now + 1 >= offer["expires_at"]:
                    continue
                context = self.context(observation, offer, at=self.world.now + 1)
                fee = offer.get("hold_fee_usd", 0)
                limit = self.number(self.program["budget_limit"], context) if fee else None
                if fee and (limit is None or observation["net_transport_spend_usd"] + observation["hotel_fee"] + fee > limit):
                    continue
                imagined = deepcopy(observation)
                imagined["virtual_minute"] = when
                imagined["net_transport_spend_usd"] += fee
                imagined["uncredited_hold_deposits_usd"] = imagined.get("uncredited_hold_deposits_usd", 0) + fee
                imagined["holds"].append(dict(offer, id="anticipated-hold", option_id=offer["id"], held_at=self.world.now + 1,
                                              expires_at=observation["horizon"], deposit_paid_usd=fee, status="held"))
                plan = self.purchase_plan(imagined, offer, booking, weather=scenario, at=when)
                if plan is not None:
                    opportunities.append((not plan["preferred"], fee, plan["expense"], offer["expires_at"], offer))
        return min(opportunities, key=lambda row: row[:4])[4] if opportunities else None

    def implement(self, plan, booking):
        """The supplied implement(); after a confirmation whose recovery window is closing, hold it while verifying."""
        offer, held = plan["option"], plan["hold"]
        if held is None:
            result = self.call("hold", id=offer["id"])
            if not result.get("ok"):
                return False
            held = result["hold"]
        if self.world.observe()["revision"] != self.revision:
            self.refresh()
        current = self.active(self.world.observe())
        revised = self.purchase_plan(self.world.observe(), self.offers[offer["id"]], current)
        if revised is None:
            return False
        if current:
            result = self.call("cancel", id=current["id"], code=self.facts["consent"])
            if not result.get("ok"):
                return False
            if self.world.observe()["revision"] != self.revision:
                self.refresh()
            revised = self.purchase_plan(self.world.observe(), self.offers[offer["id"]])
            if revised is None:
                return False
        offer, held = revised["option"], revised["hold"]
        if held is None:
            return False
        self.serial += 1
        key = "contract-booking-" + str(self.serial)
        confirmed = self.call("confirm", id=held["id"], code=self.facts["consent"], key=key).get("booking") or {}
        recovery = None
        if self.advance_preparation and confirmed.get("status") == "confirmed":
            recovery = self.recovery_opportunity(self.world.observe(), confirmed)
            if recovery is not None and recovery["expires_at"] - 2 > self.world.now:
                recovery = None  # still time: the run loop's prepare() handles it at its latest start
        if recovery is None:
            receipt = self.call("status", key=key)
        else:
            receipt, prepared = self.batch([action("status", key=key), action("hold", id=recovery["id"])])
            self.trace.append(dict(kind="preparation", strategy="one affordable recovery, held while verifying",
                                   option_id=recovery["id"], result=deepcopy(prepared)))
        if receipt.get("booking") and receipt["booking"]["status"] == "confirmed":
            booking = receipt["booking"]
            reference = booking.get("refund_contract_source", {})
            evidence = self.interpreted_documents.get(reference.get("id"))
            matches = evidence is not None and evidence["version"] == reference.get("version")
            self.booked_programs[booking["id"]] = (
                deepcopy(self.program["refund_terms"][offer["id"]]) if matches else None)
            self.booked_evidence[booking["id"]] = dict(
                purchased_source=deepcopy(reference), read_source=deepcopy(evidence), interpreted_version_matches=matches)
            return True
        return False

    def claim_pending_waiver(self, first=False):
        """Claim the current interpreted evidence once; on the first pass, hold the planned booking alongside."""
        observation = self.world.observe()
        waiver = self.facts["waiver"]
        if not observation["hotel_fee"] or waiver_key(waiver) in self.claimed:
            return
        plan = None
        if first and not self.active(observation):
            plan = self.choose_plan(dict(observation, hotel_fee=0), None)
        if plan is None or plan["hold"] is not None:
            self.batch([self.claim(waiver)])
            return
        _, held = self.batch([self.claim(waiver), action("hold", id=plan["option"]["id"])])
        if held.get("ok"):
            self.trace.append(dict(kind="planned_purchase", at=self.world.now, plan=deepcopy(plan)))
            self.implement(dict(plan, hold=held["hold"]), None)

    def run(self):
        """The supplied run loop, with claim_pending_waiver in place of its single initial claim."""
        self.refresh(initial=True)
        if self.world.finished:
            return
        self.claim_pending_waiver(first=True)
        for iteration in range(self.max_decisions):
            if self.world.finished:
                break
            observation = self.world.observe()
            if observation["revision"] != self.revision:
                current = self.active(observation)
                if current and self.advance_preparation:
                    self.prepare(observation, current)
                self.refresh()
                observation = self.world.observe()
            self.claim_pending_waiver()
            observation = self.world.observe()
            if any(booking.get("status") == "pending_verification" for booking in observation["bookings"]):
                self.call("status")
                observation = self.world.observe()
            booking = self.active(observation)
            plan = self.choose_plan(observation, booking)
            if plan:
                self.trace.append(dict(kind="planned_purchase", at=self.world.now, plan=deepcopy(plan)))
                self.implement(plan, booking)
                continue
            if observation["virtual_minute"] >= observation["handoff_minute"]:
                self.call("finish")
                break
            wake = None
            if booking and self.advance_preparation:
                wake = self.prepare(observation, booking)
                if wake == self.world.now:
                    continue
            observation = self.world.observe()
            next_time = min(observation["handoff_minute"], self.world.now + 2)
            if wake is not None and wake > self.world.now:
                next_time = min(next_time, wake)
            for forecast in self.facts["forecasts"]:
                when = forecast.get("at")
                if type(when) in (int, float) and when > self.world.now:
                    next_time = min(next_time, when)
            self.call("wait", minutes=max(1, min(36, int(next_time - self.world.now))))
        if not self.world.finished:
            self.call("finish")


def run_timely_hybrid(world, api, config, route_fn):
    """The supplied run_operational_hybrid, driving TimelyController instead of Controller."""
    traces, memory, seen_versions = [], {}, {}

    def interpret(payload):
        observation = payload["observation"]
        domains = list(dict.fromkeys(route_fn(observation, deepcopy(memory))))
        if any(domain not in ("traveler", "transport", "hotel") for domain in domains):
            raise ValueError("Route to traveler, transport, or hotel.")
        if payload.get("previous") is None:
            domains = ["traveler", "transport", "hotel"]
        scopes = role_source_ids(payload)
        for source in payload["documents"]:
            if seen_versions.get(source["id"]) != source["version"]:
                for domain, identifiers in scopes.items():
                    if source["id"] in identifiers and domain not in domains:
                        domains.append(domain)
        previous_refunds = (payload.get("previous") or {}).get("refund_terms", {})
        if set(previous_refunds) != {offer["id"] for offer in payload["offers"]} and "transport" not in domains:
            domains.append("transport")
        result = compile_contract(payload, api, config, domains, traces)
        seen_versions.update({source["id"]: source["version"] for source in payload["documents"]})
        memory.update(investigated=True, revision=observation["revision"], investigated_at=observation["virtual_minute"])
        return result

    controller = TimelyController(world, interpret, traces, refresh_context=config["refresh_context"],
                                  max_decisions=config["max_decisions"],
                                  prepare=config.get("forecast_strategy", "precaution") != "cheapest")
    controller.run()
    memory.update(documents=deepcopy(controller.documents), compiled=deepcopy(controller.program),
                  purchased_refund_terms=deepcopy(controller.booked_programs),
                  purchased_refund_evidence=deepcopy(controller.booked_evidence))
    return dict(traces=traces, working_memory=memory,
                context=dict(architecture=config["architecture"], source_versions=seen_versions))


def choose_offer_with_decisions(observation, trip_state, offers, api):
    """Optional paid proposal; solve does not call this helper by default.

    Pass only current observed offers and interpreted evidence. The result does
    not execute a booking. Recheck its suitability and tool dependencies before
    acting, and retain the returned decision in your diagnostic traces.
    """
    if api is None:
        raise ValueError("Use a model-enabled architecture when calling Decisions.")
    if not offers:
        return dict(offer_id=None, decision=None)
    bound = {f"offer_{index}": offer for index, offer in enumerate(offers)}
    if any(not isinstance(offer.get("id"), str) for offer in offers):
        raise ValueError("Pass current search offers with their observed string IDs.")
    choices = [dict(value=key, description=json.dumps(value, ensure_ascii=False))
               for key, value in bound.items()]
    choices.append(dict(value="review", description="Read or reconsider before selecting an offer."))
    decision = api.decide(
        payload=dict(observation=observation, trip_state=trip_state, offers=offers),
        questions=[dict(type="choice", name="offer", instructions=(
            "Propose a current offer using the observed requirements, transfer times, "
            "spending including retained fees, fare terms and scoped forecast evidence. "
            "Choose review if no offered proposal is suitable or evidence is missing. "
            "This selects a proposal; it does not authorize or execute a booking."), choices=choices)],
        label=dict(role="offer_proposal"), task="travel_offer_proposal")
    selected = decision["answers"][0]["choice"]
    return dict(offer_id=bound[selected]["id"] if selected in bound else None,
                decision=decision)


def route(observation, memory):
    """Choose transport, hotel and/or traveler from observed changes.

    The supplied loop passes a copy of its routing metadata, not its complete
    parsed trip state. Return domain names; edits to this argument do not persist.
    """
    return travel_route(observation, memory)


def solve(world, api, config, route_fn):
    """Retain the supplied agent, or implement your own observed-information loop.

    The delegate already owns episode-local document, trip-state, routing and
    search caches. Replace this body for a custom memory format or update policy;
    keep helper functions/classes in this file and initialize memory inside solve.
    Return serializable traces, working_memory and context for inspection. Memory
    content is not a separate scoring criterion; actual outcomes are evaluated.
    """
    if config["architecture"] == "hybrid_single" and world.observe().get("operational_sources"):
        previous_packet = None

        def interpret(settings, instructions, payload, schema, label):
            nonlocal previous_packet
            result = resolve_observed_weather(payload, previous_packet)
            if result is None:
                result = read_initial_contract(payload)
            if result is None:
                result = read_spending_amendment(payload, previous_packet)
            if result is None:
                result = (compile_partially(api, settings, instructions, payload, label, previous_packet)
                          or interpret_with_consent_references(api, settings, instructions, payload, schema, label))
                if refunds := read_weather_refunds(payload):
                    result = dict(result, refund_groups=refunds)
            previous_packet = payload
            return bind_refund_items(result)

        return run_timely_hybrid(world, SimpleNamespace(json=interpret), config, route_fn)
    return supplied_agent(world, api, config, route_fn)
